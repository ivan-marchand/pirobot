# Camera Asyncio Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Camera's `threading.Thread` capture loop with an `asyncio.Task`, eliminating the mixed threading/asyncio model.

**Architecture:** `capture_continuous` becomes an `async def` coroutine; each blocking `grab()`/`retrieve()` call is wrapped with `asyncio.to_thread`; `start_continuous_capture` creates an `asyncio.Task` via `asyncio.get_running_loop().create_task()`; the `threading.Lock` on callbacks is removed since all callbacks now run on the event loop; `WebRTCTrack.new_frame` drops `call_soon_threadsafe` and calls `queue.put_nowait` directly.

**Tech Stack:** Python 3.9, asyncio, aiohttp, OpenCV (cv2), PyAV (av), aiortc

---

## File Structure

| File | Change |
|---|---|
| `server/camera.py` | Convert capture loop to async; remove `threading.Lock`; replace `Thread` with `Task` |
| `server/webrtc.py` | Simplify `new_frame` — remove `call_soon_threadsafe` and `self._loop`; drop `import cv2` at module level |
| `server/tests/test_camera.py` | New — async camera tests |
| `server/tests/test_webrtc.py` | Fix — tests pass raw numpy to `new_frame` but it expects JPEG bytes; update drop-oldest comment |

---

### Task 1: Tests for async camera capture

**Files:**
- Create: `server/tests/test_camera.py`

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/test_camera.py
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/imarchand/git/pirobot/server
uv run python -m pytest tests/test_camera.py -v 2>&1 | head -60
```

Expected: `test_capture_continuous_is_coroutine` FAILS (`False is not true`), `test_start_continuous_capture_creates_asyncio_task` FAILS (creates a `Thread` not a `Task`), `test_no_threading_lock_on_class` FAILS (Lock still exists). The callback tests may pass already.

---

### Task 2: Async `capture_continuous` in `camera.py`

**Files:**
- Modify: `server/camera.py`

This is the main change. Read the current `camera.py` before editing — the full file is at `server/camera.py`.

- [ ] **Step 1: Replace imports at the top of `camera.py`**

Remove `threading` and `time`. Add `asyncio`. The top of the file becomes:

```python
import asyncio
import cv2
import logging
import numpy as np
import math
import platform


from handlers.base import BaseHandler
from models import Config
from motor.motor import Motor
from servo.servo_handler import ServoHandler
```

- [ ] **Step 2: Update `Camera` class variables**

Replace these two lines (around line 193 and 204):
```python
    capturing_thread = None
    ...
    streaming_frame_callbacks = threading.Lock()
```

With:
```python
    capturing_task = None
```

The full block of class variables becomes:

```python
class Camera(object):
    status = "UK"
    streaming = False
    capturing = False
    capturing_task = None
    frame_rate = 5
    overlay = True
    selected_camera = "front"
    front_capture_device = None
    back_capture_device = None
    has_camera_servo = False
    servo_id = 1
    servo_center_position = 60
    servo_position = 0
    new_streaming_frame_callbacks = {}
    available_device = None
```

- [ ] **Step 3: Remove the lock from `add_new_streaming_frame_callback` and `remove_new_streaming_frame_callback`**

Replace the two methods (currently lines ~208–219) with:

```python
    @staticmethod
    def add_new_streaming_frame_callback(name, callback):
        Camera.new_streaming_frame_callbacks[name] = callback

    @staticmethod
    def remove_new_streaming_frame_callback(name):
        Camera.new_streaming_frame_callbacks.pop(name, None)
```

- [ ] **Step 4: Rewrite `capture_continuous` as `async def`**

Replace the entire `capture_continuous` static method (lines ~245–336) with:

```python
    @staticmethod
    async def capture_continuous():
        front_capturing_device = Config.get('front_capturing_device')
        front_resolution = Config.get('front_capturing_resolution')
        front_angle = Config.get('front_capturing_angle')
        back_capturing_device = Config.get('back_capturing_device')
        back_resolution = Config.get('back_capturing_resolution')
        back_angle = Config.get('back_capturing_angle')

        Camera.front_capture_device = CaptureDevice(
            resolution=front_resolution,
            capturing_device=front_capturing_device,
            angle=front_angle
        )
        if Config.get("robot_has_back_camera") and back_capturing_device not in [None, "none"]:
            if platform.machine() in ["aarch", "aarch64"]:
                Camera.back_capture_device = CaptureDevice(
                    resolution=back_resolution,
                    capturing_device=back_capturing_device,
                    angle=back_angle
                )
            else:
                Camera.back_capture_device = Camera.front_capture_device
        else:
            Camera.back_capture_device = None

        Camera.capturing = True
        frame_delay = 1.0 / Camera.frame_rate
        try:
            while Camera.capturing:
                try:
                    await asyncio.to_thread(Camera.front_capture_device.grab)
                    if Camera.back_capture_device is not None:
                        await asyncio.to_thread(Camera.back_capture_device.grab)

                    frame_delay = 1.0 / Camera.frame_rate
                    if Camera.back_capture_device is None or Camera.selected_camera == "front":
                        frame = await asyncio.to_thread(Camera.front_capture_device.retrieve)
                        BaseHandler.emit_event(
                            topic="camera", event_type="new_front_camera_frame", data=dict(frame=frame),
                        )
                        Camera.front_capture_device.add_navigation_lines(frame)
                        Camera.front_capture_device.add_radar(frame, [50, 0], [25, 25])
                    else:
                        frame = await asyncio.to_thread(Camera.back_capture_device.retrieve)
                        BaseHandler.emit_event(
                            topic="camera", event_type="new_back_camera_frame", data=dict(frame=frame),
                        )

                    if Camera.back_capture_device is not None and Camera.overlay:
                        if Camera.selected_camera == "front":
                            overlay_frame = await asyncio.to_thread(Camera.back_capture_device.retrieve)
                            BaseHandler.emit_event(
                                topic="camera",
                                event_type="new_back_camera_frame",
                                data=dict(frame=overlay_frame, overlay=True),
                            )
                            Camera.front_capture_device.add_overlay(frame, overlay_frame, [75, 0], [25, 25])
                        else:
                            overlay_frame = await asyncio.to_thread(Camera.front_capture_device.retrieve)
                            BaseHandler.emit_event(
                                topic="camera",
                                event_type="new_front_camera_frame",
                                data=dict(frame=overlay_frame, overlay=True),
                            )
                            Camera.back_capture_device.add_overlay(frame, overlay_frame, [75, 0], [25, 25])

                    if frame is not None:
                        BaseHandler.emit_event(
                            topic="camera", event_type="new_streaming_frame", data=dict(frame=frame),
                        )

                        if Camera.streaming:
                            jpeg_bytes = cv2.imencode('.jpg', frame)[1].tobytes()
                            for callback in Camera.new_streaming_frame_callbacks.values():
                                try:
                                    callback(jpeg_bytes)
                                except Exception:
                                    logger.error("Exception in streaming frame callback", exc_info=True)

                    await asyncio.sleep(frame_delay)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.error("Unexpected exception in continuous capture", exc_info=True)
                    continue
        finally:
            if Camera.front_capture_device is not None:
                await asyncio.to_thread(Camera.front_capture_device.close)
                Camera.front_capture_device = None
            if Camera.back_capture_device is not None:
                await asyncio.to_thread(Camera.back_capture_device.close)
                Camera.back_capture_device = None
            Camera.capturing = False
            logger.info("Stop Capture")
```

- [ ] **Step 5: Rewrite `start_continuous_capture`**

Replace the method (currently lines ~338–344):

```python
    @staticmethod
    def start_continuous_capture():
        if not Camera.capturing or Camera.capturing_task is None or Camera.capturing_task.done():
            Camera.capturing = True
            logger.info("Start capture")
            Camera.capturing_task = asyncio.get_event_loop().create_task(Camera.capture_continuous())
```

- [ ] **Step 6: Run the camera tests**

```bash
cd /Users/imarchand/git/pirobot/server
uv run python -m pytest tests/test_camera.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 7: Run full server test suite**

```bash
cd /Users/imarchand/git/pirobot/server
uv run python -m pytest tests/ -v
```

Expected: all tests pass (WebRTC tests may show failures — fixed in Task 3).

- [ ] **Step 8: Commit**

```bash
cd /Users/imarchand/git/pirobot
git add server/camera.py server/tests/test_camera.py
git commit -m "refactor: replace Camera threading.Thread with asyncio.Task"
```

---

### Task 3: Simplify `WebRTCTrack.new_frame` and fix existing WebRTC tests

**Files:**
- Modify: `server/webrtc.py`
- Modify: `server/tests/test_webrtc.py`

The existing WebRTC tests call `track.new_frame(bgr_array)` passing raw numpy arrays, but `new_frame` expects JPEG bytes (as the camera sends). These tests are currently broken. Fix them here, and simultaneously simplify `new_frame` to drop `call_soon_threadsafe` since callbacks now run on the event loop.

- [ ] **Step 1: Simplify `WebRTCTrack.__init__` and `new_frame` in `webrtc.py`**

In `WebRTCTrack.__init__` (around line 103), remove the `self._loop` line:

```python
    def __init__(self):
        super().__init__()
        self._callback_key = f"webrtc_{uuid.uuid4().hex}"
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=self.QUEUE_SIZE)
        Camera.add_new_streaming_frame_callback(self._callback_key, self.new_frame)
        Camera.start_streaming()
```

Replace the entire `new_frame` method (currently lines ~111–132) with:

```python
    def new_frame(self, bgr_frame) -> None:
        """Called from the event loop — bgr_frame is JPEG-encoded bytes."""
        import cv2
        arr = cv2.imdecode(np.frombuffer(bgr_frame, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return
        rgb = arr[:, :, ::-1].copy()
        av_frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._queue.put_nowait(av_frame)
        except asyncio.QueueFull:
            pass
```

- [ ] **Step 2: Fix `test_webrtc.py` — encode test frames as JPEG before passing to `new_frame`**

`new_frame` expects JPEG bytes. Replace all three test methods that call `track.new_frame(bgr)` with versions that encode first:

```python
class TestWebRTCTrack(unittest.IsolatedAsyncioTestCase):

    def _make_jpeg(self, bgr: np.ndarray) -> bytes:
        """Encode a BGR numpy array as JPEG bytes, as the camera does."""
        import cv2
        _, buf = cv2.imencode('.jpg', bgr)
        return buf.tobytes()

    async def test_recv_returns_av_video_frame(self):
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

    async def test_pts_increments(self):
        from webrtc import WebRTCTrack
        track = WebRTCTrack()
        bgr = np.zeros((240, 320, 3), dtype=np.uint8)
        jpeg = self._make_jpeg(bgr)
        track.new_frame(jpeg)
        track.new_frame(jpeg)
        f1 = await asyncio.wait_for(track.recv(), timeout=2.0)
        f2 = await asyncio.wait_for(track.recv(), timeout=2.0)
        self.assertGreater(f2.pts, f1.pts)

    async def test_queue_drops_oldest_when_full(self):
        from webrtc import WebRTCTrack
        track = WebRTCTrack()
        bgr_first = np.full((240, 320, 3), 1, dtype=np.uint8)
        bgr_later = np.full((240, 320, 3), 2, dtype=np.uint8)
        jpeg_first = self._make_jpeg(bgr_first)
        jpeg_later = self._make_jpeg(bgr_later)

        for _ in range(WebRTCTrack.QUEUE_SIZE):
            track.new_frame(jpeg_first)
        track.new_frame(jpeg_later)  # should drop oldest

        # new_frame now calls put_nowait directly on the event loop — no sleep needed
        self.assertEqual(track._queue.qsize(), WebRTCTrack.QUEUE_SIZE)

    async def test_close_deregisters_camera_callback(self):
        from webrtc import WebRTCTrack
        from camera import Camera

        track = WebRTCTrack()
        key = track._callback_key
        self.assertIn(key, Camera.new_streaming_frame_callbacks)
        track.close()
        self.assertNotIn(key, Camera.new_streaming_frame_callbacks)
```

The full updated `test_webrtc.py` (keep `TestResolveEncoder` unchanged, replace `TestWebRTCTrack`):

```python
import asyncio
import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

sys.path.insert(0, "/Users/imarchand/git/pirobot/server")

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

    def _make_jpeg(self, bgr: np.ndarray) -> bytes:
        """Encode a BGR numpy array as JPEG bytes, as the camera does."""
        import cv2
        _, buf = cv2.imencode('.jpg', bgr)
        return buf.tobytes()

    async def test_recv_returns_av_video_frame(self):
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

    async def test_pts_increments(self):
        from webrtc import WebRTCTrack
        track = WebRTCTrack()
        bgr = np.zeros((240, 320, 3), dtype=np.uint8)
        jpeg = self._make_jpeg(bgr)
        track.new_frame(jpeg)
        track.new_frame(jpeg)
        f1 = await asyncio.wait_for(track.recv(), timeout=2.0)
        f2 = await asyncio.wait_for(track.recv(), timeout=2.0)
        self.assertGreater(f2.pts, f1.pts)

    async def test_queue_drops_oldest_when_full(self):
        from webrtc import WebRTCTrack
        track = WebRTCTrack()
        bgr_first = np.full((240, 320, 3), 1, dtype=np.uint8)
        bgr_later = np.full((240, 320, 3), 2, dtype=np.uint8)
        jpeg_first = self._make_jpeg(bgr_first)
        jpeg_later = self._make_jpeg(bgr_later)

        for _ in range(WebRTCTrack.QUEUE_SIZE):
            track.new_frame(jpeg_first)
        track.new_frame(jpeg_later)  # should drop oldest

        # new_frame calls put_nowait directly — no sleep needed
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
```

- [ ] **Step 3: Run the full server test suite**

```bash
cd /Users/imarchand/git/pirobot/server
uv run python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/imarchand/git/pirobot
git add server/webrtc.py server/tests/test_webrtc.py
git commit -m "refactor: simplify WebRTCTrack.new_frame — drop call_soon_threadsafe"
```
