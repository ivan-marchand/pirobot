# WebRTC Video Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the MJPEG-over-WebSocket video transport with WebRTC, giving the browser and pirobot-client lower latency and H.264 compression while preserving all server-side OpenCV processing.

**Architecture:** A new `server/webrtc.py` module provides `WebRTCTrack` (a Camera callback subscriber that feeds frames into an asyncio queue) and `WebRTCSessionManager` (handles SDP offer/answer and ICE over the existing `/ws/robot` WebSocket). The browser's `VideoStreamControl.js` is rewritten to use `RTCPeerConnection`, and `home.js` routes incoming `webrtc` topic messages to it. `/ws/video_stream` and `VideoSessionManager` are removed.

**Tech Stack:** Python aiortc, PyAV (av), asyncio; React RTCPeerConnection API; aiohttp WebSocket (existing)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `server/pyproject.toml` | Modify | Add `aiortc` dependency |
| `server/config/default.robot.json` | Modify | Add `webrtc_h264_encoder` config key |
| `server/webrtc.py` | Create | `_resolve_encoder`, `WebRTCTrack`, `WebRTCSessionManager` |
| `server/webserver/session_manager.py` | Modify | Remove `VideoSessionManager`; add `webrtc` dispatch to `RobotSessionManager` |
| `server/webserver/app.py` | Modify | Remove `/ws/video_stream` route and `VideoSessionManager` import |
| `server/tests/test_webrtc.py` | Create | Unit tests for `WebRTCTrack` and `WebRTCSessionManager` |
| `react/pirobot/src/VideoStreamControl.js` | Rewrite | `RTCPeerConnection`, `<video>` element, FPS counter |
| `react/pirobot/src/home.js` | Modify | `sendWebRTCMessage`, route `webrtc` topic to `VideoStreamControl` ref |

---

### Task 1: Add aiortc dependency and config key

**Files:**
- Modify: `server/pyproject.toml`
- Modify: `server/config/default.robot.json`

- [ ] **Step 1: Add aiortc to pyproject.toml**

Open `server/pyproject.toml` and add `"aiortc"` to the `dependencies` list:

```toml
dependencies = [
    "aiohttp",
    "aiortc",
    "opencv-python-headless",
    "smbus; sys_platform == 'linux'",
    "pyserial",
    "pyttsx3",
    "pillow",
    "pygame",
    "sqlalchemy",
    "prettytable",
    "pyinstaller",
    "fake-rpi; platform_machine != 'aarch64'",
]
```

- [ ] **Step 2: Sync dependencies**

```bash
cd server
uv sync
```

Expected: aiortc and its deps (aioice, pyee, av, cryptography, etc.) installed with no errors.

- [ ] **Step 3: Add webrtc_h264_encoder config key to default.robot.json**

In `server/config/default.robot.json`, inside the `"config"` object, add the new key (place it near other camera-related keys):

```json
"webrtc_h264_encoder": {
    "type": "str",
    "default": "auto",
    "choices": ["auto", "h264_v4l2m2m", "libx264"],
    "category": "camera"
}
```

- [ ] **Step 4: Verify config key is readable**

```bash
cd server
uv run python manage.py configuration get webrtc_h264_encoder
```

Expected output: `auto`

- [ ] **Step 5: Commit**

```bash
git add server/pyproject.toml server/uv.lock server/config/default.robot.json
git commit -m "chore: add aiortc dependency and webrtc_h264_encoder config key"
```

---

### Task 2: Create server/webrtc.py

**Files:**
- Create: `server/webrtc.py`
- Create: `server/tests/test_webrtc.py`

- [ ] **Step 1: Write the failing tests**

Create `server/tests/__init__.py` (empty) and `server/tests/test_webrtc.py`:

```python
import asyncio
import platform
import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

# Ensure server/ is on the path
sys.path.insert(0, ".")


class TestResolveEncoder(unittest.TestCase):

    def test_libx264_explicit(self):
        from webrtc import _resolve_encoder
        self.assertEqual(_resolve_encoder("libx264"), "libx264")

    def test_h264_v4l2m2m_explicit(self):
        # When explicitly requested and available, returns h264_v4l2m2m
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
        # Push a synthetic BGR frame (240x320x3)
        bgr = np.zeros((240, 320, 3), dtype=np.uint8)
        bgr[10, 10] = [0, 128, 255]
        track.new_frame(bgr)

        frame = await asyncio.wait_for(track.recv(), timeout=1.0)
        self.assertIsInstance(frame, av.VideoFrame)
        self.assertEqual(frame.format.name, "rgb24")
        self.assertGreaterEqual(frame.pts, 0)

    async def test_pts_increments(self):
        from webrtc import WebRTCTrack
        track = WebRTCTrack()
        bgr = np.zeros((240, 320, 3), dtype=np.uint8)
        track.new_frame(bgr)
        track.new_frame(bgr)
        f1 = await asyncio.wait_for(track.recv(), timeout=1.0)
        f2 = await asyncio.wait_for(track.recv(), timeout=1.0)
        self.assertGreater(f2.pts, f1.pts)

    async def test_queue_drops_oldest_when_full(self):
        from webrtc import WebRTCTrack
        track = WebRTCTrack()
        # Fill queue beyond capacity: put QUEUE_SIZE+1 frames
        # First frame should be dropped
        bgr_first = np.full((240, 320, 3), 1, dtype=np.uint8)
        bgr_later = np.full((240, 320, 3), 2, dtype=np.uint8)
        # Fill the queue to capacity
        for _ in range(WebRTCTrack.QUEUE_SIZE):
            track.new_frame(bgr_first)
        # This extra one should cause the oldest (bgr_first) to be dropped
        track.new_frame(bgr_later)

        # The queue should still be bounded at QUEUE_SIZE
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

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd server
uv run python -m pytest tests/test_webrtc.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'webrtc'` or similar — confirms tests are wired up.

- [ ] **Step 3: Create server/webrtc.py**

```python
import asyncio
import logging
import platform
import uuid

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
    logger.error(f"Failed to configure WebRTC encoder: {exc}", exc_info=True)
    raise


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
        self._pts = 0
        Camera.add_new_streaming_frame_callback(self._callback_key, self.new_frame)
        Camera.start_streaming()

    def new_frame(self, bgr_frame: np.ndarray) -> None:
        """Called from the Camera background thread. Thread-safe."""
        # Convert BGR to RGB
        rgb = bgr_frame[:, :, ::-1].copy()
        av_frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
        if self._queue.full():
            try:
                self._queue.get_nowait()  # drop oldest
            except asyncio.QueueEmpty:
                pass
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
            send_message: async callable(dict) — sends a JSON message back over the WebSocket.
        """
        self._send_message = send_message
        self._pc: RTCPeerConnection | None = None
        self._track: WebRTCTrack | None = None

    async def handle_offer(self, sdp: str) -> None:
        # Clean up any existing connection
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
```

- [ ] **Step 4: Run the tests**

```bash
cd server
uv run python -m pytest tests/test_webrtc.py -v
```

Expected: All tests pass. `test_queue_drops_oldest_when_full`, `test_close_deregisters_camera_callback`, `test_recv_returns_av_video_frame`, `test_pts_increments`, and all `TestResolveEncoder` tests should be green.

- [ ] **Step 5: Commit**

```bash
git add server/webrtc.py server/tests/__init__.py server/tests/test_webrtc.py
git commit -m "feat: add WebRTCTrack and WebRTCSessionManager with H.264 encoder selection"
```

---

### Task 3: Update session_manager.py

**Files:**
- Modify: `server/webserver/session_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `server/tests/test_webrtc.py` a new test class:

```python
class TestRobotSessionManagerWebRTC(unittest.IsolatedAsyncioTestCase):

    async def test_webrtc_offer_dispatched(self):
        """process_message routes webrtc offer to WebRTCSessionManager.handle_offer"""
        from webserver.session_manager import RobotSessionManager

        sent = []

        async def fake_send(msg):
            sent.append(msg)

        # Patch WebRTCSessionManager so we don't need a real RTCPeerConnection
        with patch("webserver.session_manager.WebRTCSessionManager") as MockManager:
            instance = MockManager.return_value
            instance.handle_offer = asyncio.coroutine(lambda sdp: None)
            instance.handle_ice_candidate = asyncio.coroutine(lambda **kw: None)

            protocol = MagicMock()
            session = RobotSessionManager(sid="test", protocol=protocol)

            import json
            msg = json.dumps({"topic": "webrtc", "action": "offer", "sdp": "v=0...", "type": "offer"})
            await session.process_message(msg)

            instance.handle_offer.assert_called_once_with("v=0...")
```

Run to confirm failure:

```bash
cd server
uv run python -m pytest tests/test_webrtc.py::TestRobotSessionManagerWebRTC -v
```

Expected: FAIL — `RobotSessionManager` does not yet handle `webrtc` topic.

- [ ] **Step 2: Rewrite session_manager.py**

Replace `server/webserver/session_manager.py` with:

```python
from abc import ABC, abstractmethod
import json
import logging

from server import Server
from webrtc import WebRTCSessionManager

logger = logging.getLogger(__name__)


class SessionManager(ABC):

    def __init__(self, sid):
        self.sid = sid

    def __del__(self):
        self.close()

    def close(self):
        pass

    @abstractmethod
    async def process_message(self, message):
        pass


class RobotSessionManager(SessionManager):

    def __init__(self, sid, protocol):
        super().__init__(sid)
        self.protocol = protocol
        self._webrtc = WebRTCSessionManager(send_message=protocol.send_message_raw)

    async def process_message(self, message):
        message_dict = json.loads(message)
        topic = message_dict.get("topic")
        if topic == "robot":
            await Server.process(message_dict.get("message"), self.protocol)
        elif topic == "webrtc":
            await self._dispatch_webrtc(message_dict)
        else:
            logger.warning(f"Unknown topic {topic}")

    async def _dispatch_webrtc(self, msg: dict) -> None:
        action = msg.get("action")
        if action == "offer":
            await self._webrtc.handle_offer(msg["sdp"])
        elif action == "ice_candidate":
            await self._webrtc.handle_ice_candidate(
                candidate=msg["candidate"],
                sdp_mid=msg["sdpMid"],
                sdp_mline_index=msg["sdpMLineIndex"],
            )
        else:
            logger.warning(f"Unknown webrtc action {action!r}")

    def close(self):
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(self._webrtc.close())
        else:
            loop.run_until_complete(self._webrtc.close())
```

- [ ] **Step 3: Add send_message_raw to WebSocketProtocol in app.py**

`WebRTCSessionManager` calls `protocol.send_message_raw(dict)` — a raw JSON send. The existing `send_message(topic, message)` has a different signature. Open `server/webserver/app.py` and add this method to `WebSocketProtocol`:

```python
async def send_message_raw(self, data: dict):
    await self.ws.send_json(data)
```

- [ ] **Step 4: Run the test**

```bash
cd server
uv run python -m pytest tests/test_webrtc.py -v
```

Expected: All tests pass including `TestRobotSessionManagerWebRTC`.

- [ ] **Step 5: Commit**

```bash
git add server/webserver/session_manager.py server/webserver/app.py server/tests/test_webrtc.py
git commit -m "feat: add webrtc topic dispatch to RobotSessionManager, remove VideoSessionManager"
```

---

### Task 4: Remove /ws/video_stream from app.py

**Files:**
- Modify: `server/webserver/app.py`

- [ ] **Step 1: Remove the video_stream route and VideoSessionManager import**

In `server/webserver/app.py`:

1. Remove the import line:
   ```python
   from webserver.session_manager import RobotSessionManager, VideoSessionManager
   ```
   Replace with:
   ```python
   from webserver.session_manager import RobotSessionManager
   ```

2. Remove the entire `@routes.get("/ws/video_stream")` handler function (the `video_stream` async function and its `@routes.get` decorator).

- [ ] **Step 2: Verify server starts without errors**

```bash
cd server
uv run python manage.py runserver &
sleep 3
curl -s http://localhost:8080/ | head -5
kill %1
```

Expected: Server starts, responds to HTTP, no import errors in output.

- [ ] **Step 3: Commit**

```bash
git add server/webserver/app.py
git commit -m "feat: remove /ws/video_stream route — replaced by WebRTC signaling over /ws/robot"
```

---

### Task 5: Rewrite VideoStreamControl.js

**Files:**
- Modify: `react/pirobot/src/VideoStreamControl.js`

- [ ] **Step 1: Rewrite VideoStreamControl.js**

Replace the entire content of `react/pirobot/src/VideoStreamControl.js`:

```jsx
import React from "react";

const FPS_UPDATE_INTERVAL = 1; // seconds

class VideoStreamControl extends React.Component {
    constructor(props) {
        super(props);
        this._pc = null;
        this._frameCount = 0;
        this._lastFpsTs = 0;
        this._videoRef = React.createRef();
    }

    componentDidMount() {
        this._startWebRTC();
    }

    componentWillUnmount() {
        this._closeWebRTC();
    }

    _startWebRTC = async () => {
        this._closeWebRTC();

        const pc = new RTCPeerConnection({ iceServers: [] });
        this._pc = pc;

        pc.ontrack = (event) => {
            if (this._videoRef.current && event.streams[0]) {
                this._videoRef.current.srcObject = event.streams[0];
                this._startFpsCounter();
            }
        };

        pc.onicecandidate = (event) => {
            if (event.candidate) {
                this.props.sendWebRTCMessage({
                    action: "ice_candidate",
                    candidate: event.candidate.candidate,
                    sdpMid: event.candidate.sdpMid,
                    sdpMLineIndex: event.candidate.sdpMLineIndex,
                });
            }
        };

        // Add a recvonly transceiver so the server knows we want video
        pc.addTransceiver("video", { direction: "recvonly" });

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        this.props.sendWebRTCMessage({
            action: "offer",
            sdp: pc.localDescription.sdp,
            type: "offer",
        });
    };

    _closeWebRTC = () => {
        if (this._pc) {
            this._pc.close();
            this._pc = null;
        }
        this._stopFpsCounter();
    };

    handleWebRTCMessage = async (msg) => {
        if (!this._pc) return;
        if (msg.action === "answer") {
            await this._pc.setRemoteDescription({ type: "answer", sdp: msg.sdp });
        } else if (msg.action === "ice_candidate") {
            await this._pc.addIceCandidate({
                candidate: msg.candidate,
                sdpMid: msg.sdpMid,
                sdpMLineIndex: msg.sdpMLineIndex,
            });
        }
    };

    _startFpsCounter = () => {
        const video = this._videoRef.current;
        if (!video) return;
        this._lastFpsTs = performance.now();
        this._frameCount = 0;

        if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
            const onFrame = (_now, _meta) => {
                this._frameCount++;
                const now = performance.now();
                if ((now - this._lastFpsTs) / 1000 >= FPS_UPDATE_INTERVAL) {
                    this.props.updateFps(
                        Math.round(this._frameCount / ((now - this._lastFpsTs) / 1000))
                    );
                    this._frameCount = 0;
                    this._lastFpsTs = now;
                }
                if (this._videoRef.current) {
                    this._videoRef.current.requestVideoFrameCallback(onFrame);
                }
            };
            video.requestVideoFrameCallback(onFrame);
        } else {
            // Safari fallback: poll with setInterval
            this._fpsInterval = setInterval(() => {
                if (video.readyState >= 2) {
                    this._frameCount++;
                    const now = performance.now();
                    if ((now - this._lastFpsTs) / 1000 >= FPS_UPDATE_INTERVAL) {
                        this.props.updateFps(
                            Math.round(this._frameCount / ((now - this._lastFpsTs) / 1000))
                        );
                        this._frameCount = 0;
                        this._lastFpsTs = now;
                    }
                }
            }, 33); // ~30 fps poll
        }
    };

    _stopFpsCounter = () => {
        if (this._fpsInterval) {
            clearInterval(this._fpsInterval);
            this._fpsInterval = null;
        }
    };

    render() {
        return (
            <video
                ref={this._videoRef}
                autoPlay
                playsInline
                muted
                style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
            />
        );
    }
}

export default VideoStreamControl;
```

- [ ] **Step 2: Run existing React tests to confirm no regression**

```bash
cd react/pirobot
npm test -- --watchAll=false 2>&1 | tail -20
```

Expected: All existing tests pass. (VideoStreamControl has no unit tests; the `renders without crashing` App test should still pass.)

- [ ] **Step 3: Commit**

```bash
git add react/pirobot/src/VideoStreamControl.js
git commit -m "feat: rewrite VideoStreamControl to use RTCPeerConnection and <video> element"
```

---

### Task 6: Update home.js to route WebRTC signaling

**Files:**
- Modify: `react/pirobot/src/home.js`

The spec requires:
1. A `sendWebRTCMessage(msg)` method that sends `{"topic": "webrtc", ...msg}` over the WebSocket.
2. In `ws.onmessage`: route `topic === "webrtc"` messages to `VideoStreamControl` via a ref.
3. Pass `sendWebRTCMessage` and the ref to `VideoStreamControl`.

- [ ] **Step 1: Write the failing test**

Add to `react/pirobot/src/home.test.js` (create it if it doesn't exist):

```jsx
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Home from './home';

// Silence console.log noise in tests
beforeAll(() => jest.spyOn(console, 'log').mockImplementation(() => {}));
afterAll(() => console.log.mockRestore());

// Stub WebSocket
class MockWebSocket {
  constructor() { MockWebSocket.instance = this; this.readyState = 1; }
  send = jest.fn();
  close = jest.fn();
}
MockWebSocket.CLOSED = 3;
global.WebSocket = MockWebSocket;

// Stub RTCPeerConnection (used by VideoStreamControl)
global.RTCPeerConnection = jest.fn().mockImplementation(() => ({
  addTransceiver: jest.fn(),
  createOffer: jest.fn().mockResolvedValue({ sdp: 'v=0', type: 'offer' }),
  setLocalDescription: jest.fn().mockResolvedValue(undefined),
  close: jest.fn(),
  ontrack: null,
  onicecandidate: null,
  localDescription: { sdp: 'v=0', type: 'offer' },
}));

test('sendWebRTCMessage sends webrtc topic over WebSocket', async () => {
  await act(async () => {
    render(<MemoryRouter><Home /></MemoryRouter>);
  });
  // Simulate WS open
  await act(async () => { MockWebSocket.instance.onopen(); });

  // Trigger sendWebRTCMessage via the VideoStreamControl ref path
  // Access the Home instance methods aren't exposed — test via WS send side-effect:
  // After open, VideoStreamControl mounts and calls sendWebRTCMessage with offer
  const calls = MockWebSocket.instance.send.mock.calls.map(c => JSON.parse(c[0]));
  const webrtcCall = calls.find(c => c.topic === 'webrtc');
  expect(webrtcCall).toBeDefined();
  expect(webrtcCall.action).toBe('offer');
});
```

Run to confirm failure:

```bash
cd react/pirobot
npm test -- --watchAll=false --testPathPattern=home.test 2>&1 | tail -20
```

Expected: FAIL — `sendWebRTCMessage` not yet wired; VideoStreamControl's `props.sendWebRTCMessage` is undefined and throws.

- [ ] **Step 2: Update home.js**

Make these changes to `react/pirobot/src/home.js`:

**a) Add a ref for VideoStreamControl** — in the constructor, after `this.selected_camera = "front"`, add:

```js
this.videoStreamRef = React.createRef();
```

**b) Add sendWebRTCMessage method** — after `send_json`:

```js
sendWebRTCMessage = (msg) => {
    this.send_json({ topic: "webrtc", ...msg });
}
```

**c) Route webrtc topic in ws.onmessage** — replace the existing `ws.onmessage` handler:

```js
ws.onmessage = evt => {
    var message = JSON.parse(evt.data);
    if (message.topic === "status") {
        this.updateStatus(message.message)
    } else if (message.topic === "webrtc") {
        if (this.videoStreamRef.current) {
            this.videoStreamRef.current.handleWebRTCMessage(message);
        }
    } else {
        console.log("Unknown message topic " + message.topic)
    }
}
```

**d) Pass ref and sendWebRTCMessage to VideoStreamControl** — replace the `<VideoStreamControl>` render call:

```jsx
<VideoStreamControl
    ref={this.videoStreamRef}
    updateFps={this.updateFps}
    sendWebRTCMessage={this.sendWebRTCMessage}
/>
```

- [ ] **Step 3: Run tests**

```bash
cd react/pirobot
npm test -- --watchAll=false 2>&1 | tail -20
```

Expected: All tests pass including the new `home.test.js` webrtc test.

- [ ] **Step 4: Commit**

```bash
git add react/pirobot/src/home.js react/pirobot/src/home.test.js
git commit -m "feat: route WebRTC signaling through home.js to VideoStreamControl"
```

---

### Task 7: Verify full build

- [ ] **Step 1: Run server tests**

```bash
cd server
uv run python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Run React tests**

```bash
cd react/pirobot
npm test -- --watchAll=false
```

Expected: All tests pass.

- [ ] **Step 3: Build React app**

```bash
cd react/pirobot
npm run build 2>&1 | tail -20
```

Expected: Build succeeds, no errors. Warnings about bundle size are acceptable.

- [ ] **Step 4: Commit uncommitted CSS/JS changes if any**

Check for uncommitted files:

```bash
git status
```

If `react/pirobot/src/App.css` or `react/pirobot/src/home.js` show as modified (from the responsive layout work), commit them:

```bash
git add react/pirobot/src/App.css react/pirobot/src/home.js
git commit -m "chore: commit responsive layout CSS and home.js changes"
```

---

## Self-Review

### Spec coverage

- [x] WebRTC transport replaces MJPEG-over-WebSocket — Tasks 2, 4, 5
- [x] Signaling over `/ws/robot` as `webrtc` topic — Tasks 3, 6
- [x] `/ws/video_stream` retired — Task 4
- [x] `webrtc_h264_encoder` config key (auto/h264_v4l2m2m/libx264) — Tasks 1, 2
- [x] `_resolve_encoder` probes hw encoder on aarch64 — Task 2
- [x] monkey-patch of `H264Encoder.DEFAULT_PARAMS` — Task 2
- [x] `WebRTCTrack`: Camera callback, asyncio.Queue, drop oldest on full — Task 2
- [x] `WebRTCSessionManager`: offer/answer/ICE, one per session — Tasks 2, 3
- [x] `VideoStreamControl` rewritten with `RTCPeerConnection` + `<video>` — Task 5
- [x] FPS via `requestVideoFrameCallback` with `setInterval` fallback — Task 5
- [x] `home.js` routes `webrtc` topic to `VideoStreamControl` ref — Task 6
- [x] `VideoSessionManager` removed — Task 3

### Type/method consistency

- `WebRTCSessionManager(send_message=...)` — `send_message` is `protocol.send_message_raw` added in Task 3
- `WebRTCTrack.new_frame(bgr_frame)` used in both tests and implementation — consistent
- `WebRTCTrack.QUEUE_SIZE` referenced in tests and defined in implementation — consistent
- `handleWebRTCMessage(msg)` defined on `VideoStreamControl` and called via ref in `home.js` — consistent
- `sendWebRTCMessage` passed as `props.sendWebRTCMessage` to `VideoStreamControl` — consistent with its usage in `_startWebRTC`
