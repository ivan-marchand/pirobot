import asyncio
import logging
import platform
import uuid
from typing import Optional

import av
import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import VideoStreamTrack

from camera import Camera
from models import Config

logger = logging.getLogger(__name__)


def _encoder_available(codec_name: str) -> bool:
    """Return True if the given FFmpeg encoder name is usable."""
    try:
        ctx = av.CodecContext.create(codec_name, "w")
        ctx.close()
        return True
    except Exception:
        return False


def _resolve_encoder(config_value: str) -> str:
    """Return the FFmpeg encoder name to use based on config_value."""
    if config_value == "libx264":
        return "libx264"
    if config_value == "h264_v4l2m2m":
        if not _encoder_available("h264_v4l2m2m"):
            raise RuntimeError(
                "webrtc_h264_encoder is set to h264_v4l2m2m but the encoder is not available. "
                "Check that FFmpeg was built with V4L2 support."
            )
        return "h264_v4l2m2m"
    if config_value == "auto":
        if platform.machine() == "aarch64" and _encoder_available("h264_v4l2m2m"):
            return "h264_v4l2m2m"
        return "libx264"
    raise ValueError(f"Unknown webrtc_h264_encoder value: {config_value!r}")


# Apply hardware encoder patch once at module init, before any RTCPeerConnection is created.
try:
    import aiortc.codecs.h264 as _h264
    _selected_encoder = _resolve_encoder(Config.get("webrtc_h264_encoder"))
    if _selected_encoder != "libx264":
        _h264.H264Encoder.DEFAULT_PARAMS = {
            **_h264.H264Encoder.DEFAULT_PARAMS,
            "codec": _selected_encoder,
        }
    logger.info(f"WebRTC H.264 encoder: {_selected_encoder}")
except Exception as exc:
    logger.warning(f"Could not configure WebRTC encoder ({exc}), falling back to libx264")


class WebRTCTrack(VideoStreamTrack):
    """
    A VideoStreamTrack that pulls OpenCV frames from the Camera via callback
    and delivers them as av.VideoFrame to aiortc.
    """

    QUEUE_SIZE = 5

    def __init__(self):
        super().__init__()
        self._callback_key = f"webrtc_{uuid.uuid4().hex}"
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=self.QUEUE_SIZE)
        self._loop = asyncio.get_event_loop()
        Camera.add_new_streaming_frame_callback(self._callback_key, self.new_frame)
        Camera.start_streaming()

    def new_frame(self, bgr_frame: np.ndarray) -> None:
        """Called from the Camera background thread or event loop. Thread-safe."""
        rgb = bgr_frame[:, :, ::-1].copy()
        av_frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
        if self._queue.full():
            try:
                self._queue.get_nowait()  # drop oldest
            except asyncio.QueueEmpty:
                pass
        try:
            # If already running in the event loop, call directly.
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is self._loop:
            self._queue.put_nowait(av_frame)
        else:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, av_frame)

    async def recv(self) -> av.VideoFrame:
        frame = await self._queue.get()
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base
        return frame

    def close(self) -> None:
        Camera.remove_new_streaming_frame_callback(self._callback_key)


class WebRTCSessionManager:
    """
    One instance per /ws/robot session.
    Handles WebRTC signaling (offer/answer/ICE) and owns the RTCPeerConnection.
    """

    def __init__(self, send_message):
        """
        Args:
            send_message: async callable(dict) that sends a JSON message back over the WebSocket.
        """
        self._send_message = send_message
        self._pc: Optional[RTCPeerConnection] = None
        self._track: Optional[WebRTCTrack] = None

    async def handle_offer(self, sdp: str) -> None:
        await self._close_connection()

        self._pc = RTCPeerConnection()
        self._track = WebRTCTrack()
        self._pc.addTrack(self._track)

        @self._pc.on("icecandidate")
        async def on_ice_candidate(candidate):
            if candidate:
                await self._send_message({
                    "topic": "webrtc",
                    "action": "ice_candidate",
                    "candidate": candidate.candidate,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex,
                })

        offer = RTCSessionDescription(sdp=sdp, type="offer")
        await self._pc.setRemoteDescription(offer)
        answer = await self._pc.createAnswer()
        await self._pc.setLocalDescription(answer)

        await self._send_message({
            "topic": "webrtc",
            "action": "answer",
            "sdp": self._pc.localDescription.sdp,
            "type": "answer",
        })

    async def handle_ice_candidate(self, candidate: str, sdp_mid: str, sdp_mline_index: int) -> None:
        if self._pc is None:
            logger.warning("Received ICE candidate before offer — ignoring")
            return
        from aiortc import RTCIceCandidate
        ice = RTCIceCandidate(
            component=None,
            foundation=None,
            ip=None,
            port=None,
            priority=None,
            protocol=None,
            type=None,
            sdpMid=sdp_mid,
            sdpMLineIndex=sdp_mline_index,
        )
        ice._candidate = candidate
        await self._pc.addIceCandidate(ice)

    async def close(self) -> None:
        await self._close_connection()

    async def _close_connection(self) -> None:
        if self._track is not None:
            self._track.close()
            self._track = None
        if self._pc is not None:
            await self._pc.close()
            self._pc = None
