import asyncio
import inspect
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "/Users/imarchand/git/pirobot/server")

from camera import Camera


class TestCameraAsyncCapture(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Reset Camera state between tests."""
        Camera.capturing = False
        Camera.capturing_task = None

    def test_capture_continuous_is_coroutine(self):
        """capture_continuous must be an async def, not a sync function."""
        self.assertTrue(inspect.iscoroutinefunction(Camera.capture_continuous))

    async def test_start_continuous_capture_creates_asyncio_task(self):
        """start_continuous_capture must create an asyncio.Task, not a threading.Thread."""
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
        async def _mock_capture():
            await asyncio.sleep(100)

        with patch.object(Camera, 'capture_continuous', _mock_capture):
            Camera.start_continuous_capture()
            first_task = Camera.capturing_task
            await asyncio.sleep(0)  # let task start before second call
            Camera.start_continuous_capture()  # second call — must not create new task
            self.assertIs(Camera.capturing_task, first_task)
            first_task.cancel()
            try:
                await first_task
            except asyncio.CancelledError:
                pass

    async def test_capturing_stops_when_flag_cleared(self):
        """Setting Camera.capturing = False causes the capture loop to exit."""
        async def _mock_capture():
            while Camera.capturing:
                await asyncio.sleep(0.005)

        with patch.object(Camera, 'capture_continuous', _mock_capture):
            Camera.capturing = True
            Camera.start_continuous_capture()
            self.assertFalse(Camera.capturing_task.done())
            Camera.capturing = False
            await asyncio.wait_for(Camera.capturing_task, timeout=1.0)
            self.assertTrue(Camera.capturing_task.done())

    def test_no_threading_lock_on_class(self):
        """streaming_frame_callbacks (the old Lock) must not exist on Camera after refactor."""
        self.assertFalse(
            hasattr(Camera, 'streaming_frame_callbacks'),
            "Camera.streaming_frame_callbacks must be removed entirely after refactor",
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
