import asyncio
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import numpy as np

# Ensure server/ is on the path
sys.path.insert(0, "/Users/imarchand/git/pirobot/server")

# Pre-import webrtc so that patch("webrtc._encoder_available", ...) can resolve
# the module without triggering a fresh import (which would cascade through
# camera.py's platform.machine() check while platform.machine is already patched).
import webrtc  # noqa: E402


class TestResolveEncoder(unittest.TestCase):

    def test_libx264_explicit(self):
        from webrtc import _resolve_encoder
        self.assertEqual(_resolve_encoder("libx264"), "libx264")

    def test_h264_v4l2m2m_explicit_available(self):
        with patch("webrtc._encoder_available", return_value=True):
            from webrtc import _resolve_encoder
            self.assertEqual(_resolve_encoder("h264_v4l2m2m"), "h264_v4l2m2m")

    def test_auto_non_aarch64_returns_libx264(self):
        with patch("platform.machine", return_value="x86_64"):
            from webrtc import _resolve_encoder
            self.assertEqual(_resolve_encoder("auto"), "libx264")

    def test_auto_aarch64_with_hw_returns_hw(self):
        with patch("platform.machine", return_value="aarch64"), \
             patch("webrtc._encoder_available", return_value=True):
            from webrtc import _resolve_encoder
            self.assertEqual(_resolve_encoder("auto"), "h264_v4l2m2m")

    def test_auto_aarch64_without_hw_falls_back(self):
        with patch("platform.machine", return_value="aarch64"), \
             patch("webrtc._encoder_available", return_value=False):
            from webrtc import _resolve_encoder
            self.assertEqual(_resolve_encoder("auto"), "libx264")

    def test_h264_v4l2m2m_unavailable_raises(self):
        with patch("webrtc._encoder_available", return_value=False):
            from webrtc import _resolve_encoder
            with self.assertRaises(RuntimeError):
                _resolve_encoder("h264_v4l2m2m")


@patch('webrtc.Camera.stop_streaming')
@patch('webrtc.Camera.start_streaming')
class TestWebRTCTrack(unittest.IsolatedAsyncioTestCase):

    def _make_jpeg(self, bgr: np.ndarray) -> bytes:
        """Encode a BGR numpy array as JPEG bytes, as the camera does."""
        import cv2
        _, buf = cv2.imencode('.jpg', bgr)
        return buf.tobytes()

    async def test_recv_returns_av_video_frame(self, mock_start, mock_stop):
        from webrtc import WebRTCTrack
        import av

        track = WebRTCTrack()
        bgr = np.zeros((240, 320, 3), dtype=np.uint8)
        bgr[10, 10] = [0, 128, 255]
        track.new_frame(self._make_jpeg(bgr))

        frame = await asyncio.wait_for(track.recv(), timeout=2.0)
        self.assertIsInstance(frame, av.VideoFrame)
        self.assertEqual(frame.format.name, "rgb24")
        self.assertGreaterEqual(frame.pts, 0)

    async def test_pts_increments(self, mock_start, mock_stop):
        from webrtc import WebRTCTrack
        track = WebRTCTrack()
        bgr = np.zeros((240, 320, 3), dtype=np.uint8)
        jpeg = self._make_jpeg(bgr)
        track.new_frame(jpeg)
        track.new_frame(jpeg)
        f1 = await asyncio.wait_for(track.recv(), timeout=2.0)
        f2 = await asyncio.wait_for(track.recv(), timeout=2.0)
        self.assertGreater(f2.pts, f1.pts)

    async def test_queue_drops_oldest_when_full(self, mock_start, mock_stop):
        from webrtc import WebRTCTrack
        track = WebRTCTrack()
        bgr_first = np.full((240, 320, 3), 1, dtype=np.uint8)
        bgr_later = np.full((240, 320, 3), 255, dtype=np.uint8)
        jpeg_first = self._make_jpeg(bgr_first)
        jpeg_later = self._make_jpeg(bgr_later)

        for _ in range(WebRTCTrack.QUEUE_SIZE):
            track.new_frame(jpeg_first)
        track.new_frame(jpeg_later)  # should push out an oldest frame

        self.assertEqual(track._queue.qsize(), WebRTCTrack.QUEUE_SIZE)
        # Drain all frames and verify the last one is from bgr_later
        frames = []
        while not track._queue.empty():
            frames.append(track._queue.get_nowait())
        last_frame = frames[-1]
        # The last inserted frame should be from bgr_later (all-255 pixels)
        arr = last_frame.to_ndarray(format="rgb24")
        self.assertGreater(arr.mean(), 200, "Last frame should be mostly white (from bgr_later)")

    async def test_close_deregisters_camera_callback(self, mock_start, mock_stop):
        from webrtc import WebRTCTrack
        from camera import Camera

        track = WebRTCTrack()
        key = track._callback_key
        self.assertIn(key, Camera.new_streaming_frame_callbacks)
        track.close()
        self.assertNotIn(key, Camera.new_streaming_frame_callbacks)


@patch('webrtc._sounddevice_available', True)
class TestRobotMicTrack(unittest.IsolatedAsyncioTestCase):

    async def test_recv_returns_audio_frame(self):
        import av
        import numpy as np

        # Simulate what the sounddevice callback would enqueue
        with patch('webrtc.sd') as mock_sd:
            # Make InputStream a no-op context
            mock_sd.InputStream.return_value.__enter__ = lambda s: s
            mock_sd.InputStream.return_value.__exit__ = lambda *a: None
            mock_sd.InputStream.return_value.start = lambda: None

            from webrtc import RobotMicTrack
            track = RobotMicTrack()
            # Manually enqueue a PCM frame (960 samples of zeros)
            pcm = np.zeros(960, dtype=np.int16)
            track._queue.put_nowait(pcm)

            frame = await asyncio.wait_for(track.recv(), timeout=2.0)
            self.assertIsInstance(frame, av.AudioFrame)
            self.assertEqual(frame.sample_rate, 48000)
            self.assertGreaterEqual(frame.pts, 0)


class TestBrowserAudioPlayer(unittest.IsolatedAsyncioTestCase):

    def _make_mock_proc(self):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.close = MagicMock()
        mock_proc.terminate = MagicMock()
        mock_proc.wait = AsyncMock()
        return mock_proc

    async def test_stop_cancels_task(self):
        with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=self._make_mock_proc())):
            from webrtc import BrowserAudioPlayer
            player = BrowserAudioPlayer()
            mock_track = MagicMock()
            mock_track.recv = AsyncMock(side_effect=asyncio.CancelledError())
            player.start(mock_track)
            self.assertIsNotNone(player._task)
            await asyncio.sleep(0)
            player.stop()
            self.assertIsNone(player._task)

    async def test_first_frame_logs_format_info(self):
        import av
        call_count = 0

        frame = av.AudioFrame(format='s16', layout='mono', samples=960)
        frame.sample_rate = 48000
        frame.pts = 0

        async def recv_impl():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return frame
            await asyncio.sleep(10)  # block so the task doesn't race past the assert

        mock_track = MagicMock()
        mock_track.recv = recv_impl

        with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=self._make_mock_proc())), \
             self.assertLogs('webrtc', level='INFO') as captured:
            from webrtc import BrowserAudioPlayer
            player = BrowserAudioPlayer()
            player.start(mock_track)
            await asyncio.sleep(0.05)
            player.stop()
            await asyncio.sleep(0.05)

        first_frame_logs = [msg for msg in captured.output if 'first frame' in msg]
        self.assertEqual(len(first_frame_logs), 1,
            f"Expected exactly one 'first frame' log, got {len(first_frame_logs)}: {captured.output}"
        )


class TestBrowserVideoReceiver(unittest.IsolatedAsyncioTestCase):

    async def test_stop_cancels_task(self):
        from unittest.mock import AsyncMock
        from webrtc import BrowserVideoReceiver
        receiver = BrowserVideoReceiver()

        mock_track = MagicMock()
        mock_track.recv = AsyncMock(side_effect=asyncio.CancelledError())

        with patch('webrtc.BaseHandler') as mock_bh:
            mock_bh.get_handler.return_value = None
            receiver.start(mock_track)
            self.assertIsNotNone(receiver._task)
            await asyncio.sleep(0)
            receiver.stop()
            self.assertIsNone(receiver._task)


class TestWebRTCSessionManagerTalkingMode(unittest.IsolatedAsyncioTestCase):

    def _make_mock_pc(self):
        from unittest.mock import AsyncMock
        mock_pc = MagicMock()
        mock_pc.setRemoteDescription = AsyncMock()
        mock_pc.createAnswer = AsyncMock(return_value=MagicMock(sdp="answer_sdp"))
        mock_pc.setLocalDescription = AsyncMock()
        mock_pc.localDescription = MagicMock(sdp="answer_sdp")
        mock_pc.on = MagicMock(side_effect=lambda event: (lambda fn: fn))
        mock_pc.close = AsyncMock()
        return mock_pc

    async def test_handle_offer_talking_creates_mic_track(self):
        with patch('webrtc._sounddevice_available', True), \
             patch('webrtc.RobotMicTrack') as MockMicTrack, \
             patch('webrtc.BrowserAudioPlayer') as MockPlayer, \
             patch('webrtc.BrowserVideoReceiver') as MockReceiver, \
             patch('webrtc.RTCPeerConnection') as MockPC, \
             patch('webrtc.WebRTCTrack'):

            from unittest.mock import AsyncMock
            MockPC.return_value = self._make_mock_pc()

            from webrtc import WebRTCSessionManager
            session = WebRTCSessionManager(send_message=AsyncMock())
            await session.handle_offer(sdp="fake_sdp", talking=True)

            MockMicTrack.assert_called_once()
            MockPlayer.assert_called_once()
            MockReceiver.assert_called_once()

    async def test_handle_offer_not_talking_skips_audio(self):
        with patch('webrtc._sounddevice_available', True), \
             patch('webrtc.RobotMicTrack') as MockMicTrack, \
             patch('webrtc.BrowserAudioPlayer') as MockPlayer, \
             patch('webrtc.BrowserVideoReceiver') as MockReceiver, \
             patch('webrtc.RTCPeerConnection') as MockPC, \
             patch('webrtc.WebRTCTrack'):

            from unittest.mock import AsyncMock
            MockPC.return_value = self._make_mock_pc()

            from webrtc import WebRTCSessionManager
            session = WebRTCSessionManager(send_message=AsyncMock())
            await session.handle_offer(sdp="fake_sdp", talking=False)

            MockMicTrack.assert_not_called()
            MockPlayer.assert_not_called()
            MockReceiver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
