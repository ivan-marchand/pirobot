import asyncio
import fractions as _fractions
import logging
import platform
import uuid
from typing import Optional

import numpy as np

import av
import aiortc.codecs.h264 as _h264
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import AudioStreamTrack, MediaStreamError, VideoStreamTrack

from camera import Camera
from handlers.base import BaseHandler
from models import Config

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
    _sounddevice_available = True
except ImportError:
    logger.debug("sounddevice not available — robot microphone and speaker disabled (Pi only)")
    _sounddevice_available = False
    sd = None


def _encoder_available(codec_name: str) -> bool:
    """Return True if the given FFmpeg encoder name is usable."""
    try:
        av.CodecContext.create(codec_name, "w")
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


_selected_encoder: Optional[str] = None


def _get_encoder() -> str:
    """Return the selected encoder, initializing on first call."""
    global _selected_encoder
    if _selected_encoder is not None:
        return _selected_encoder

    try:
        _selected_encoder = _resolve_encoder(Config.get("webrtc_h264_encoder"))
    except Exception as exc:
        logger.warning(f"Could not read webrtc_h264_encoder config ({exc}), using libx264")
        _selected_encoder = "libx264"

    if _selected_encoder != "libx264":
        _MAX_FRAME_RATE = _h264.MAX_FRAME_RATE

        def _patched_encode_frame(self, frame: av.VideoFrame, force_keyframe: bool):
            if self.codec and (
                frame.width != self.codec.width
                or frame.height != self.codec.height
                or abs(self.target_bitrate - self.codec.bit_rate) / max(1, self.codec.bit_rate) > 0.1
            ):
                self.buffer_data = b""
                self.buffer_pts = None
                self.codec = None

            if force_keyframe:
                frame.pict_type = av.video.frame.PictureType.I
            else:
                frame.pict_type = av.video.frame.PictureType.NONE

            if self.codec is None:
                self.codec = av.CodecContext.create(_selected_encoder, "w")
                self.codec.width = frame.width
                self.codec.height = frame.height
                self.codec.bit_rate = self.target_bitrate
                self.codec.pix_fmt = "yuv420p"
                self.codec.framerate = _fractions.Fraction(_MAX_FRAME_RATE, 1)
                self.codec.time_base = _fractions.Fraction(1, _MAX_FRAME_RATE)
                self.codec.options = {"tune": "zerolatency", "level": "31"}
                self.codec.profile = "Baseline"

            data_to_send = b""
            for package in self.codec.encode(frame):
                data_to_send += bytes(package)

            if data_to_send:
                yield from self._split_bitstream(data_to_send)

        _h264.H264Encoder._encode_frame = _patched_encode_frame

    logger.info(f"WebRTC H.264 encoder: {_selected_encoder}")
    return _selected_encoder


class RobotMicTrack(AudioStreamTrack):
    """Captures audio from the Pi microphone at 48 kHz mono via sounddevice."""

    SAMPLE_RATE = 48000
    CHANNELS = 1
    SAMPLES_PER_FRAME = 960  # 20 ms at 48 kHz

    def __init__(self):
        super().__init__()
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._sd_stream = None
        self._loop = asyncio.get_event_loop()

    def _start_sd_stream(self) -> None:
        def _callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"RobotMicTrack sounddevice status: {status}")
            pcm = (indata[:, 0] * 32767).astype(np.int16)

            def _enqueue(data):
                if self._queue.full():
                    try:
                        self._queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    self._queue.put_nowait(data)
                except asyncio.QueueFull:
                    pass

            self._loop.call_soon_threadsafe(_enqueue, pcm.copy())

        self._sd_stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            dtype="float32",
            blocksize=self.SAMPLES_PER_FRAME,
            callback=_callback,
        )
        self._sd_stream.start()

    async def recv(self) -> av.AudioFrame:
        if self._sd_stream is None:
            self._start_sd_stream()
        pcm = await self._queue.get()
        frame = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = self.SAMPLE_RATE
        if hasattr(self, "_timestamp"):
            self._timestamp += self.SAMPLES_PER_FRAME
        else:
            self._timestamp = 0
        frame.pts = self._timestamp
        frame.time_base = _fractions.Fraction(1, self.SAMPLE_RATE)
        return frame

    def stop(self) -> None:
        if self._sd_stream is not None:
            self._sd_stream.stop()
            self._sd_stream.close()
            self._sd_stream = None


class BrowserAudioPlayer:
    """Plays incoming browser audio frames by piping raw PCM to aplay.

    Bypasses sounddevice/PortAudio entirely — aplay handles buffering and
    ALSA device access in its own process, completely off the event loop.
    """

    def __init__(self):
        self._task: Optional[asyncio.Task] = None

    def start(self, track) -> None:
        self._task = asyncio.ensure_future(self._receive(track))

    _SAMPLE_RATE = 48000
    _BYTES_PER_SEC = _SAMPLE_RATE * 2  # 16-bit mono = 96000 bytes/sec
    _APLAY_BUFFER_SEC = 0.2            # -B 200000 = 200 ms ALSA pre-buffer
    _MAX_AHEAD_SEC = 0.3               # drop frames if >300 ms ahead of playback clock

    async def _receive(self, track) -> None:
        import time
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "aplay", "-f", "S16_LE", "-r", "48000", "-c", "1", "-t", "raw",
                "-B", "200000",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            logger.info("BrowserAudioPlayer: aplay started")
            start_time: Optional[float] = None
            bytes_written = 0
            _first_frame_logged = False
            while True:
                try:
                    frame = await track.recv()
                    arr = frame.to_ndarray()
                    pcm_bytes = arr.flatten().astype(np.int16).tobytes()

                    if not _first_frame_logged:
                        logger.info(
                            f"BrowserAudioPlayer: first frame — "
                            f"format={frame.format.name}, "
                            f"sample_rate={frame.sample_rate}, "
                            f"samples={frame.samples}, "
                            f"channels={len(frame.layout.channels)}, "
                            f"ndarray shape={arr.shape}, "
                            f"dtype={arr.dtype}"
                        )
                        _first_frame_logged = True

                    now = time.monotonic()
                    if start_time is None:
                        start_time = now

                    # Estimate bytes aplay has consumed (wall-clock minus initial buffer fill)
                    elapsed = now - start_time
                    bytes_played = max(0.0, elapsed - self._APLAY_BUFFER_SEC) * self._BYTES_PER_SEC
                    buffer_depth_sec = (bytes_written - bytes_played) / self._BYTES_PER_SEC

                    if buffer_depth_sec > self._MAX_AHEAD_SEC:
                        continue  # drop — we're ahead of playback, prevent lag buildup

                    proc.stdin.write(pcm_bytes)
                    bytes_written += len(pcm_bytes)
                except asyncio.CancelledError:
                    raise
                except MediaStreamError:
                    break
                except Exception as exc:
                    logger.warning(f"BrowserAudioPlayer frame error: {type(exc).__name__}: {exc}")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"BrowserAudioPlayer: failed to start aplay: {exc}")
        finally:
            if proc is not None:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except Exception:
                    pass

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None


class BrowserVideoReceiver:
    """Forwards incoming browser webcam frames to the LCD handler.

    LCD updates are rate-limited and offloaded to a thread — SPI writes are
    blocking and take ~50-100ms; running them on the event loop would stall
    everything else.
    """

    _LCD_FPS = 5  # SPI bus can't sustain more than ~5-10 FPS at 240x320

    def __init__(self):
        self._task: Optional[asyncio.Task] = None

    def start(self, track) -> None:
        self._task = asyncio.ensure_future(self._receive(track))

    async def _receive(self, track) -> None:
        loop = asyncio.get_running_loop()
        frame_interval = 1.0 / self._LCD_FPS
        last_lcd_update = 0.0
        try:
            while True:
                try:
                    frame = await track.recv()
                    now = loop.time()
                    if now - last_lcd_update < frame_interval:
                        continue
                    lcd = BaseHandler.get_handler("lcd")
                    if lcd is not None and lcd.eligible:
                        img = frame.to_ndarray(format="rgb24")
                        await asyncio.to_thread(lcd.display_frame, img)
                        last_lcd_update = loop.time()
                except asyncio.CancelledError:
                    raise
                except MediaStreamError:
                    break
                except Exception as exc:
                    logger.warning(f"BrowserVideoReceiver frame error: {type(exc).__name__}: {exc}", exc_info=True)
        except asyncio.CancelledError:
            pass
        finally:
            lcd = BaseHandler.get_handler("lcd")
            if lcd is not None and lcd.eligible:
                lcd.stop_video()

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None


class WebRTCTrack(VideoStreamTrack):
    """
    A VideoStreamTrack that pulls raw BGR frames from the Camera via callback
    and delivers them as av.VideoFrame to aiortc.
    """

    QUEUE_SIZE = 1

    def __init__(self):
        super().__init__()
        _get_encoder()  # initialize encoder selection (and apply H264 patch) on first use
        self._callback_key = f"webrtc_{uuid.uuid4().hex}"
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=self.QUEUE_SIZE)
        Camera.add_new_streaming_frame_callback(self._callback_key, self.new_frame)
        Camera.start_streaming()

    def new_frame(self, bgr_frame) -> None:
        """Called from the event loop — bgr_frame is a raw BGR numpy array."""
        av_frame = av.VideoFrame.from_ndarray(bgr_frame, format="bgr24")
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._queue.put_nowait(av_frame)
        except asyncio.QueueFull:
            pass

    async def recv(self) -> av.VideoFrame:
        frame = await self._queue.get()
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base
        return frame

    def close(self) -> None:
        Camera.remove_new_streaming_frame_callback(self._callback_key)
        Camera.stop_streaming()


class WebRTCSessionManager:
    """
    One instance per /ws/robot session.
    Handles WebRTC signaling (offer/answer/ICE) and owns the RTCPeerConnection.
    """

    def __init__(self, send_message):
        self._send_message = send_message
        self._pc: Optional[RTCPeerConnection] = None
        self._track: Optional[WebRTCTrack] = None
        self._mic_track: Optional[RobotMicTrack] = None
        self._audio_player: Optional[BrowserAudioPlayer] = None
        self._video_receiver: Optional[BrowserVideoReceiver] = None

    async def handle_offer(self, sdp: str, talking: bool = False) -> None:
        await self._close_connection()

        self._pc = RTCPeerConnection()
        self._track = WebRTCTrack()
        self._pc.addTrack(self._track)

        if talking and _sounddevice_available:
            self._mic_track = RobotMicTrack()
            self._pc.addTrack(self._mic_track)
            self._audio_player = BrowserAudioPlayer()
            self._video_receiver = BrowserVideoReceiver()

            @self._pc.on("track")
            async def on_track(track):
                if track.kind == "audio" and self._audio_player is not None:
                    self._audio_player.start(track)
                elif track.kind == "video" and self._video_receiver is not None:
                    self._video_receiver.start(track)

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
        if not candidate:
            return
        try:
            from aiortc.sdp import candidate_from_sdp
            sdp_line = candidate[len("candidate:"):] if candidate.startswith("candidate:") else candidate
            ice = candidate_from_sdp(sdp_line)
            ice.sdpMid = sdp_mid
            ice.sdpMLineIndex = sdp_mline_index
            await self._pc.addIceCandidate(ice)
        except Exception as exc:
            logger.warning(f"Failed to add ICE candidate ({exc}): {candidate!r}")

    async def close(self) -> None:
        await self._close_connection()

    async def _close_connection(self) -> None:
        if self._mic_track is not None:
            self._mic_track.stop()
            self._mic_track = None
        if self._audio_player is not None:
            self._audio_player.stop()
            self._audio_player = None
        if self._video_receiver is not None:
            self._video_receiver.stop()
            self._video_receiver = None
        if self._track is not None:
            self._track.close()
            self._track = None
        if self._pc is not None:
            await self._pc.close()
            self._pc = None
