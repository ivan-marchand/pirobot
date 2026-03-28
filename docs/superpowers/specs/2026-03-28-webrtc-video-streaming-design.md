# WebRTC Video Streaming

**Date:** 2026-03-28
**Status:** Approved

## Goal

Replace the current MJPEG-over-WebSocket video transport (`/ws/video_stream`) with WebRTC, giving both the browser UI and `pirobot-client` lower latency and better compression (H.264 vs per-frame JPEG). Server-side OpenCV processing is preserved unchanged. Recording and picture capture continue to happen on the server.

## Scope

- **In scope:** video transport only. Robot control, recording, capture, and all other handlers are untouched.
- **Out of scope:** STUN/TURN infrastructure (VPN covers the internet case). Multi-peer optimisation via `MediaRelay` (can be added later if needed).

---

## H.264 Encoder Selection

aiortc uses `libx264` (software) by default. On the Raspberry Pi, `h264_v4l2m2m` (V4L2 Memory-to-Memory hardware encoder) is available via FFmpeg/PyAV and significantly reduces CPU usage.

**Strategy: platform-aware encoder with software fallback.**

`WebRTCTrack` selects the encoder at construction time:

```python
import platform
import av

def _select_h264_encoder() -> str:
    if platform.machine() == "aarch64":
        try:
            # probe whether the hardware encoder is available
            codec = av.CodecContext.create("h264_v4l2m2m", "w")
            codec.close()
            return "h264_v4l2m2m"
        except Exception:
            pass
    return "libx264"
```

aiortc's internal `H264Encoder` class hardcodes `libx264`. To use the hardware encoder, `webrtc.py` monkey-patches the encoder before creating any peer connection:

```python
import aiortc.codecs.h264 as _h264

_ENCODER = _select_h264_encoder()
if _ENCODER != "libx264":
    _h264.H264Encoder.DEFAULT_PARAMS = {
        **_h264.H264Encoder.DEFAULT_PARAMS,
        "codec": _ENCODER,
    }
```

This is a known limitation of aiortc (no first-class hardware encoder API). The patch is applied once at module import and is safe as long as all peer connections in the process use the same encoder — which is the case here.

**Hardware encoder options on Pi:**

| Encoder | Pi 3 | Pi 4 | Pi 5 | Notes |
|---|---|---|---|---|
| `h264_v4l2m2m` | ✓ | ✓ | ✓ | V4L2 M2M, available on all Pi models with FFmpeg |
| `libx264` (fallback) | ✓ | ✓ | ✓ | Software, ~30–50% CPU at 640×480 30fps on Pi 4 |

**macOS development:** `h264_v4l2m2m` is not available; the probe fails and `libx264` is used automatically. No code changes needed for dev vs production.

---

## Architecture

```
Camera (OpenCV capture + processing)
    │
    ├── BaseHandler.emit_event("camera", "new_streaming_frame")
    │       └── CameraHandler — recording, picture capture (unchanged)
    │
    └── WebRTCTrack.new_frame() callback (new, one per connected client)
            └── asyncio.Queue (thread-safe handoff)
                    └── WebRTCTrack.recv() → av.VideoFrame
                            └── aiortc RTCPeerConnection
                                    └── H.264 RTP → browser / pirobot-client
```

Signaling travels over the existing `/ws/robot` WebSocket as a new `"webrtc"` topic. No new HTTP endpoints are added. `/ws/video_stream` is retired.

---

## Signaling Flow

All messages use the existing WebSocket message envelope:

**Offer (client → server):**
```json
{"topic": "webrtc", "action": "offer", "sdp": "...", "type": "offer"}
```

**Answer (server → client):**
```json
{"topic": "webrtc", "action": "answer", "sdp": "...", "type": "answer"}
```

**ICE candidate (either direction):**
```json
{"topic": "webrtc", "action": "ice_candidate", "candidate": "...", "sdpMid": "...", "sdpMLineIndex": 0}
```

---

## Components

### Server

#### `server/webrtc.py` (new)

**`WebRTCTrack(VideoStreamTrack)`**
- Registers itself as a Camera frame callback on construction; deregisters on close.
- `new_frame(frame)`: called from the Camera background thread. Converts the OpenCV BGR frame to RGB, creates an `av.VideoFrame`, puts it onto a bounded `asyncio.Queue` via `loop.call_soon_threadsafe(queue.put_nowait, frame)`. If the queue is full, drops the oldest frame to prevent unbounded memory growth.
- `recv()`: awaits the queue and returns the next `av.VideoFrame` with correct `pts` and `time_base` (via `next_timestamp()`).

**`WebRTCSessionManager`**
- One instance per `/ws/robot` session.
- `handle_offer(sdp)`: creates `RTCPeerConnection`, instantiates `WebRTCTrack`, adds track to connection, generates and returns SDP answer.
- `handle_ice_candidate(candidate)`: adds ICE candidate to the connection.
- `close()`: closes `RTCPeerConnection` and `WebRTCTrack` (which deregisters the Camera callback).
- Collects ICE candidates via `pc.on("icecandidate")` and sends them back over the WebSocket.

#### `server/webserver/session_manager.py` (modified)

- Remove `VideoSessionManager` class entirely.
- `RobotSessionManager.process_message()`: add `elif topic == "webrtc"` branch that dispatches to the session's `WebRTCSessionManager`.

#### `server/webserver/app.py` (modified)

- Remove `/ws/video_stream` route and `VideoSessionManager` import.
- Each `RobotSessionManager` instance owns a `WebRTCSessionManager`.

#### `server/pyproject.toml` (modified)

- Add `"aiortc"` to dependencies.

---

### Browser — `react/pirobot/src/VideoStreamControl.js` (rewritten)

- Replace WebSocket + base64 decode with `RTCPeerConnection`.
- On mount:
  1. Create `RTCPeerConnection` with no ICE servers (local/VPN only).
  2. Create SDP offer, set as local description.
  3. Send offer to server via `props.sendWebRTCMessage()` callback.
  4. On `track` event: attach `event.streams[0]` to a `<video>` ref.
- Handle incoming `"webrtc"` messages forwarded from `home.js`:
  - `"answer"`: set remote description.
  - `"ice_candidate"`: add ICE candidate.
- On unmount: close `RTCPeerConnection`.
- Render: `<video ref={...} autoPlay playsInline muted style={{ width: '100%', height: '100%', objectFit: 'contain' }} />` — replaces `<img>`.
- FPS: count frames using `video.requestVideoFrameCallback()` (Chrome/Edge) with a `setInterval`-based fallback for Safari.

### Browser — `react/pirobot/src/home.js` (modified)

- Add `sendWebRTCMessage(msg)` method: sends `{"topic": "webrtc", ...msg}` over `this.state.ws`.
- In `ws.onmessage`: handle `message.topic === "webrtc"` — forward to `VideoStreamControl` via a ref.
- Pass `sendWebRTCMessage` and a `ref` down to `VideoStreamControl`.

---

### `pirobot-client` (modified)

- Replace the `/ws/video_stream` WebSocket connection with an `aiortc` `RTCPeerConnection`.
- Signaling over the existing `/ws/robot` connection: send offer, receive answer and ICE candidates using the same JSON envelope as the browser.
- Frame consumption loop:
  ```python
  track = pc.getReceivers()[0].track
  while True:
      frame = await track.recv()          # av.VideoFrame
      img = frame.to_ndarray(format="bgr24")  # numpy array, same as before
      self.change_pixmap_signal.emit(img)
  ```
- Recording and capture commands continue to be sent over `/ws/robot` as today — no change.

---

## Data Flow (steady state)

```
Camera background thread
  → OpenCV processing (navigation lines, radar, face detection)
  → WebRTCTrack.new_frame()          [thread boundary: call_soon_threadsafe]
  → asyncio.Queue
  → WebRTCTrack.recv()               [aiortc calls this]
  → av.VideoFrame (RGB)
  → aiortc H.264 encode
  → RTP over UDP
  → browser <video> / pirobot-client numpy frame
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Camera not yet started | `recv()` blocks on queue; frames arrive once camera starts |
| Camera restart | Frames stop briefly, resume automatically; WebRTC connection stays open |
| ICE failure | Client sends a new offer over the WebSocket to re-establish |
| Multiple clients | Each session gets its own `WebRTCTrack` + `RTCPeerConnection`; frames encoded independently |
| Queue full (client too slow) | Oldest frame dropped; bounded queue prevents memory growth |
| WebSocket close | `WebRTCSessionManager.close()` called; `RTCPeerConnection` and Camera callback cleaned up |

---

## Testing

### Server unit tests
- `WebRTCTrack.recv()` returns `av.VideoFrame` with valid `pts`/`time_base`
- Queue drops oldest frame when full
- Camera callback deregistered on `WebRTCTrack.close()`
- `WebRTCSessionManager` produces valid SDP answer from a well-formed offer

### Browser manual tests
- `<video>` plays without stutter on desktop and mobile (landscape)
- FPS counter updates correctly
- Reconnect: restart server → browser re-offers and video resumes

### `pirobot-client` manual tests
- Qt window displays video after handshake
- `to_ndarray(format="bgr24")` frame shape/dtype matches existing Qt rendering expectations
- `start_video` and `capture_picture` still save files on the robot

### Regression
- All robot control commands (drive, arm, lights, etc.) unaffected
- `CameraHandler` recording/capture events still fire correctly
