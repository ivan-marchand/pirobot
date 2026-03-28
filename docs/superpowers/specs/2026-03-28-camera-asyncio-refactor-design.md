# Camera Asyncio Refactor

**Date:** 2026-03-28
**Status:** Approved

## Goal

Replace `Camera`'s `threading.Thread` capture loop with an `asyncio.Task`, eliminating the mixed threading/asyncio model. All frame capture, processing, and callback dispatch runs on the event loop; blocking OpenCV calls are offloaded via `asyncio.to_thread`.

## Motivation

The server is fully async (`aiohttp`, `aiortc`). The camera background thread is the only remaining use of `threading`. Unifying on asyncio removes the need for `threading.Lock` on callbacks, simplifies `WebRTCTrack` (no more `call_soon_threadsafe`), and makes the capture loop pausable and cancellable via standard asyncio primitives.

---

## Scope

- **In scope:** `server/camera.py` and `server/webrtc.py` (simplify `WebRTCTrack.new_frame`).
- **Out of scope:** `CaptureDevice` internals, `BaseHandler.emit_event`, all handlers.

---

## Architecture

```
asyncio event loop
  ├── capture_continuous() [asyncio.Task]
  │     ├── await asyncio.to_thread(device.grab)      # releases loop during I/O
  │     ├── await asyncio.sleep(frame_delay)           # rate limiting
  │     ├── await asyncio.to_thread(device.retrieve)  # releases loop during I/O
  │     ├── frame processing (sync, fast — runs on loop)
  │     ├── BaseHandler.emit_event(...)                # unchanged
  │     └── for cb in new_streaming_frame_callbacks.values(): cb(frame)  # direct, no lock
  │
  └── WebRTCTrack.new_frame(frame)  [called directly on loop]
        └── queue.put_nowait(av_frame)                 # safe — same thread
```

`CaptureDevice.grab()` and `.retrieve()` remain plain synchronous methods. `asyncio.to_thread` wraps the call sites in `capture_continuous`, not the methods themselves.

---

## Changes

### `server/camera.py`

**Class variables:**
- Remove: `capturing_thread`, `streaming_frame_callbacks` (the `threading.Lock`)
- Add: `capturing_task: Optional[asyncio.Task]` (replaces `capturing_thread`)
- Keep: `new_streaming_frame_callbacks` dict (unchanged)

**`capture_continuous`** — becomes `async def`:
- `device.grab()` → `await asyncio.to_thread(device.grab)`
- Busy-wait frame-rate loop → `await asyncio.sleep(frame_delay)` (computed once per iteration based on elapsed time vs target interval)
- `device.retrieve()` → `await asyncio.to_thread(device.retrieve)`
- Frame processing (`add_navigation_lines`, `add_radar`, `add_overlay`) stays synchronous — these are fast CPU ops
- Callback dispatch: `Lock.acquire/release` removed; callbacks called directly
- Error handler: remove `if Camera.streaming_frame_callbacks.locked(): release()` — no lock to release

**`start_continuous_capture`** — becomes `async def`:
- `threading.Thread(...)` → `asyncio.get_running_loop().create_task(Camera.capture_continuous())`
- Alive check: `not Camera.capturing_task.done()` (replaces `capturing_thread.is_alive()`)

**`add_new_streaming_frame_callback` / `remove_new_streaming_frame_callback`** — remove `Lock.acquire/release` calls; dict mutation is safe on the event loop.

**`stop_continuous_capture`** — unchanged (sets `Camera.capturing = False`, which the async loop checks).

**Imports removed:** `threading`, `time`
**Imports added:** `asyncio`

### `server/webrtc.py`

**`WebRTCTrack.__init__`** — remove `self._loop = asyncio.get_event_loop()`.

**`WebRTCTrack.new_frame`** — callbacks now called on the event loop directly, so `call_soon_threadsafe` is no longer needed:

```python
def new_frame(self, bgr_frame) -> None:
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

---

## Callers of `start_continuous_capture`

`start_continuous_capture` is called from:
- `Camera.start_streaming()` — called from `WebRTCTrack.__init__` (async context ✓)
- `CameraHandler` — async handler methods ✓

Both are already async contexts, so `await Camera.start_continuous_capture()` works without changes to callers beyond adding `await`.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| `grab()` raises | `except Exception` in loop logs and continues |
| `retrieve()` raises | Same |
| Task cancelled | `asyncio.CancelledError` propagates out of `capture_continuous`; devices closed in `finally` block |
| Callback raises | Wrapped in try/except inside dispatch loop; logs and continues |

The `finally` block in `capture_continuous` closes devices (currently at end of while loop — moved to `finally` to handle cancellation cleanly).

---

## Testing

- `capture_continuous` yields control between frames (event loop not blocked)
- Callbacks are called on the event loop (no lock needed, verified by running from async test)
- `WebRTCTrack.new_frame` puts frames onto queue without `call_soon_threadsafe`
- `start_continuous_capture` creates a task (not a thread)
- `stop_continuous_capture` + setting `capturing = False` stops the loop cleanly
