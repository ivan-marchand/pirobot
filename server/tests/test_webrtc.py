import asyncio
import sys
import unittest
from unittest.mock import patch
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


if __name__ == "__main__":
    unittest.main()
