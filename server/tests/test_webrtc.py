import asyncio
import sys
import unittest
from unittest.mock import MagicMock, patch
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


class TestWebRTCTrack(unittest.IsolatedAsyncioTestCase):

    async def test_recv_returns_av_video_frame(self):
        from webrtc import WebRTCTrack
        import av

        track = WebRTCTrack()
        bgr = np.zeros((240, 320, 3), dtype=np.uint8)
        bgr[10, 10] = [0, 128, 255]
        track.new_frame(bgr)

        frame = await asyncio.wait_for(track.recv(), timeout=2.0)
        self.assertIsInstance(frame, av.VideoFrame)
        self.assertEqual(frame.format.name, "rgb24")
        self.assertGreaterEqual(frame.pts, 0)

    async def test_pts_increments(self):
        from webrtc import WebRTCTrack
        track = WebRTCTrack()
        bgr = np.zeros((240, 320, 3), dtype=np.uint8)
        track.new_frame(bgr)
        track.new_frame(bgr)
        f1 = await asyncio.wait_for(track.recv(), timeout=2.0)
        f2 = await asyncio.wait_for(track.recv(), timeout=2.0)
        self.assertGreater(f2.pts, f1.pts)

    async def test_queue_drops_oldest_when_full(self):
        from webrtc import WebRTCTrack
        track = WebRTCTrack()
        bgr_first = np.full((240, 320, 3), 1, dtype=np.uint8)
        bgr_later = np.full((240, 320, 3), 2, dtype=np.uint8)
        for _ in range(WebRTCTrack.QUEUE_SIZE):
            track.new_frame(bgr_first)
        track.new_frame(bgr_later)
        # Flush event loop to process call_soon_threadsafe callbacks
        await asyncio.sleep(0)
        await asyncio.sleep(0)  # two yields to ensure all scheduled callbacks run
        self.assertEqual(track._queue.qsize(), WebRTCTrack.QUEUE_SIZE)

    async def test_close_deregisters_camera_callback(self):
        from webrtc import WebRTCTrack
        from camera import Camera

        track = WebRTCTrack()
        key = track._callback_key
        self.assertIn(key, Camera.new_streaming_frame_callbacks)
        track.close()
        self.assertNotIn(key, Camera.new_streaming_frame_callbacks)


if __name__ == "__main__":
    unittest.main()
