import asyncio
import inspect
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "/Users/imarchand/git/pirobot/server")

from camera import Camera


class TestCameraAsyncCapture(unittest.IsolatedAsyncioTestCase):

    def test_capture_continuous_is_coroutine(self):
        """capture_continuous must be an async def, not a sync function."""
        self.assertTrue(inspect.iscoroutinefunction(Camera.capture_continuous))

    async def test_start_continuous_capture_creates_asyncio_task(self):
        """start_continuous_capture must create an asyncio.Task, not a threading.Thread."""
        Camera.capturing = False
        Camera.capturing_task = None

        async def _mock_capture():
            await asyncio.sleep(100)

        with patch.object(Camera, 'capture_continuous', _mock_capture):
            Camera.start_continuous_capture()
            self.assertIsNotNone(Camera.capturing_task)
            self.assertIsInstance(Camera.capturing_task, asyncio.Task)
            Camera.capturing_task.cancel()
            try:
                await Camera.capturing_task
            except asyncio.CancelledError:
                pass

    async def test_start_continuous_capture_skips_if_already_running(self):
        """start_continuous_capture must not create a second task if one is running."""
        Camera.capturing = False
        Camera.capturing_task = None

        async def _mock_capture():
            await asyncio.sleep(100)

        with patch.object(Camera, 'capture_continuous', _mock_capture):
            Camera.start_continuous_capture()
            first_task = Camera.capturing_task
            Camera.start_continuous_capture()  # second call
            self.assertIs(Camera.capturing_task, first_task)
            first_task.cancel()
            try:
                await first_task
            except asyncio.CancelledError:
                pass

    async def test_capturing_stops_when_flag_cleared(self):
        """Setting Camera.capturing = False causes the capture loop to exit."""
        Camera.capturing = False
        Camera.capturing_task = None

        async def _mock_capture():
            while Camera.capturing:
                await asyncio.sleep(0.005)

        with patch.object(Camera, 'capture_continuous', _mock_capture):
            Camera.start_continuous_capture()
            self.assertFalse(Camera.capturing_task.done())
            Camera.capturing = False
            await asyncio.sleep(0.02)
            self.assertTrue(Camera.capturing_task.done())

    def test_no_threading_lock_on_class(self):
        """streaming_frame_callbacks (the old Lock) must not exist on Camera."""
        import threading
        # After refactor, Camera has no threading.Lock class variable
        self.assertFalse(
            isinstance(getattr(Camera, 'streaming_frame_callbacks', None), threading.Lock),
            "Camera.streaming_frame_callbacks should not be a threading.Lock after refactor",
        )

    def test_add_remove_callback_without_lock(self):
        """add/remove callback must work without acquiring a threading.Lock."""
        called = []

        def cb(frame):
            called.append(frame)

        Camera.add_new_streaming_frame_callback("test_cb", cb)
        self.assertIn("test_cb", Camera.new_streaming_frame_callbacks)

        # Call the callback directly (simulates event-loop dispatch)
        Camera.new_streaming_frame_callbacks["test_cb"](b"fake_jpeg")
        self.assertEqual(called, [b"fake_jpeg"])

        Camera.remove_new_streaming_frame_callback("test_cb")
        self.assertNotIn("test_cb", Camera.new_streaming_frame_callbacks)


if __name__ == "__main__":
    unittest.main()
