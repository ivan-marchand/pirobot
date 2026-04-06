# Browser Audio Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add in-call mute/camera-off PiP overlay controls (Feature 1) and a toolbar listen-to-robot-mic button (Feature 2).

**Architecture:** Feature 1 is pure frontend state in `VideoStreamControl` — toggling `track.enabled` on the local stream, no renegotiation. Feature 2 adds a `listening` prop that flows from `home.js` → `VideoStreamControl` → WebRTC offer → `session_manager.py` → `webrtc.py`, triggering a connection restart to add/remove the `RobotMicTrack`.

**Tech Stack:** React 18, MUI icons, aiortc (Python), React Testing Library, pytest

---

## File Map

| File | Change |
|---|---|
| `react/pirobot/src/VideoStreamControl.js` | Add `muted`/`cameraOff` state; PiP overlay controls; accept `listening` prop; update `_startWebRTC` and `componentDidUpdate` |
| `react/pirobot/src/home.js` | Add `listening` state; `toggleListening`; listen toolbar button gated on `robot_has_microphone` |
| `server/webrtc.py` | `handle_offer` accepts `listening: bool = False`; adds `RobotMicTrack` when `talking or listening` |
| `server/webserver/session_manager.py` | Extract `listening` from offer message; pass to `handle_offer` |
| `react/pirobot/src/VideoStreamControl.test.js` | New tests for mute/camera buttons and listen prop |
| `react/pirobot/src/home.test.js` | New tests for listen button visibility and toggle |
| `server/tests/test_webrtc.py` | New test for `listening=True` adding mic track |

---

## Task 1: Feature 1 — PiP overlay controls tests

**Files:**
- Test: `react/pirobot/src/VideoStreamControl.test.js`

- [ ] **Step 1: Add three failing tests**

Append to the end of `react/pirobot/src/VideoStreamControl.test.js`:

```js
test('renders mute and camera buttons when talking=true', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  expect(screen.getByRole('button', { name: /mute microphone/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /turn off camera/i })).toBeInTheDocument();
});

test('clicking mute button toggles aria-label', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  const muteBtn = screen.getByRole('button', { name: /mute microphone/i });
  fireEvent.click(muteBtn);
  expect(screen.getByRole('button', { name: /unmute microphone/i })).toBeInTheDocument();
});

test('clicking camera button shows camera-off placeholder', () => {
  render(<VideoStreamControl {...baseProps} talking={true} />);
  const camBtn = screen.getByRole('button', { name: /turn off camera/i });
  fireEvent.click(camBtn);
  expect(screen.getByTestId('camera-off-placeholder')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /turn on camera/i })).toBeInTheDocument();
});
```

Add the `screen` and `fireEvent` import (update existing import line):

```js
import { render, screen, fireEvent } from '@testing-library/react';
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd react/pirobot && CI=true npm test -- --watchAll=false --testPathPattern=VideoStreamControl
```

Expected: 3 new tests FAIL with "Unable to find an accessible element with the role 'button' and name /mute microphone/"

---

## Task 2: Feature 1 — PiP overlay controls implementation

**Files:**
- Modify: `react/pirobot/src/VideoStreamControl.js`

- [ ] **Step 1: Add MUI icon imports and state**

Add at the top of `VideoStreamControl.js` (after the existing `import React from "react";` line):

```js
import IconButton from '@mui/material/IconButton';
import MicIcon from '@mui/icons-material/Mic';
import MicOffIcon from '@mui/icons-material/MicOff';
import VideocamIcon from '@mui/icons-material/Videocam';
import VideocamOffIcon from '@mui/icons-material/VideocamOff';
```

In the constructor, add state initialisation after `this._pipRef = React.createRef();`:

```js
this.state = {
    muted: false,
    cameraOff: false,
};
```

- [ ] **Step 2: Add toggle handlers**

Add these two methods before the `render()` method:

```js
toggleMuted = () => {
    const track = this._localStream?.getAudioTracks()[0];
    if (track) track.enabled = !track.enabled;
    this.setState({ muted: !this.state.muted });
};

toggleCamera = () => {
    const track = this._localStream?.getVideoTracks()[0];
    if (track) track.enabled = !track.enabled;
    this.setState({ cameraOff: !this.state.cameraOff });
};
```

- [ ] **Step 3: Reset state on new session**

In `_startWebRTC`, add this line immediately after `this._closeWebRTC();`:

```js
this.setState({ muted: false, cameraOff: false });
```

- [ ] **Step 4: Replace the PiP video element with the overlay container**

In `render()`, replace the existing PiP block:

```jsx
{this.props.talking && (
    <video
        ref={this._pipRef}
        autoPlay
        playsInline
        muted
        style={{
            position: "absolute",
            bottom: 8,
            right: 8,
            width: 120,
            height: 90,
            objectFit: "cover",
            borderRadius: 4,
            border: "2px solid white",
        }}
    />
)}
```

With the new PiP container:

```jsx
{this.props.talking && (
    <div style={{
        position: "absolute",
        bottom: 8,
        right: 8,
        width: 120,
        height: 90,
        borderRadius: 4,
        border: "2px solid white",
        overflow: "hidden",
    }}>
        {this.state.cameraOff && (
            <div
                data-testid="camera-off-placeholder"
                style={{
                    position: "absolute",
                    inset: 0,
                    background: "#111",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                }}
            >
                <VideocamOffIcon style={{ color: "white", fontSize: 32 }} />
            </div>
        )}
        <video
            ref={this._pipRef}
            autoPlay
            playsInline
            muted
            style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
                display: this.state.cameraOff ? "none" : "block",
            }}
        />
        <div style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            background: "rgba(0,0,0,0.45)",
            display: "flex",
            justifyContent: "center",
        }}>
            <IconButton
                size="small"
                onClick={this.toggleMuted}
                aria-label={this.state.muted ? "Unmute microphone" : "Mute microphone"}
                sx={{ color: "white", padding: "2px" }}
            >
                {this.state.muted
                    ? <MicOffIcon fontSize="small" />
                    : <MicIcon fontSize="small" />}
            </IconButton>
            <IconButton
                size="small"
                onClick={this.toggleCamera}
                aria-label={this.state.cameraOff ? "Turn on camera" : "Turn off camera"}
                sx={{ color: "white", padding: "2px" }}
            >
                {this.state.cameraOff
                    ? <VideocamOffIcon fontSize="small" />
                    : <VideocamIcon fontSize="small" />}
            </IconButton>
        </div>
    </div>
)}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd react/pirobot && CI=true npm test -- --watchAll=false --testPathPattern=VideoStreamControl
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add react/pirobot/src/VideoStreamControl.js react/pirobot/src/VideoStreamControl.test.js
git commit -m "feat: add PiP mute and camera-off overlay controls"
```

---

## Task 3: Feature 2 — Listen button in home.js (tests + implementation)

**Files:**
- Modify: `react/pirobot/src/home.js`
- Test: `react/pirobot/src/home.test.js`

- [ ] **Step 1: Write failing tests**

Append to `react/pirobot/src/home.test.js`:

```js
test('listen button is not visible when robot_has_microphone is not set', () => {
  wrap(<Home />);
  expect(screen.queryByRole('button', { name: /listen to robot/i })).not.toBeInTheDocument();
});

test('listen button is visible when robot_config.robot_has_microphone is true', () => {
  const ws = new MockWebSocket();
  global.WebSocket = jest.fn(() => ws);
  const { unmount } = wrap(<Home />);
  act(() => {
    ws.onmessage({ data: JSON.stringify({
      topic: "status",
      message: { config: { robot_has_microphone: true }, robot_name: "TestBot", status: {} },
    })});
  });
  expect(screen.getByRole('button', { name: /listen to robot/i })).toBeInTheDocument();
  unmount();
  global.WebSocket = MockWebSocket;
});

test('listen button toggles to stop listening on click', () => {
  const ws = new MockWebSocket();
  global.WebSocket = jest.fn(() => ws);
  const { unmount } = wrap(<Home />);
  act(() => {
    ws.onmessage({ data: JSON.stringify({
      topic: "status",
      message: { config: { robot_has_microphone: true }, robot_name: "TestBot", status: {} },
    })});
  });
  fireEvent.click(screen.getByRole('button', { name: /listen to robot/i }));
  expect(screen.getByRole('button', { name: /stop listening/i })).toBeInTheDocument();
  unmount();
  global.WebSocket = MockWebSocket;
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd react/pirobot && CI=true npm test -- --watchAll=false --testPathPattern=home.test
```

Expected: 3 new tests FAIL

- [ ] **Step 3: Add VolumeUp/VolumeOff imports to home.js**

Add after the existing `MicOffIcon` import line:

```js
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import VolumeOffIcon from '@mui/icons-material/VolumeOff';
```

- [ ] **Step 4: Add listening state and toggle method to home.js**

In the constructor's `this.state`, add `listening: false`:

```js
this.state = {
    ws: null,
    fps: 0,
    robot_config: {},
    robot_name: null,
    robot_status: {},
    control: "joystick",
    control_arm: false,
    drive_slow_mode: false,
    talking: false,
    listening: false,
};
```

Add `toggleListening` after `toggleTalking`:

```js
toggleListening = () => {
    this.setState({ listening: !this.state.listening });
}
```

- [ ] **Step 5: Add listen button to toolbar in home.js**

In `render()`, find the existing mic button block:

```jsx
{this.state.robot_config.robot_has_microphone && <Divider orientation="vertical" flexItem/>}
{this.state.robot_config.robot_has_microphone && (
    <Tooltip title={this.state.talking ? "Stop talking" : "Start talking"}>
        <IconButton onClick={this.toggleTalking}>
            {this.state.talking ? <MicOffIcon /> : <MicIcon />}
        </IconButton>
    </Tooltip>
)}
```

Replace it with (adds the listen button immediately after the talk button):

```jsx
{this.state.robot_config.robot_has_microphone && <Divider orientation="vertical" flexItem/>}
{this.state.robot_config.robot_has_microphone && (
    <Tooltip title={this.state.talking ? "Stop talking" : "Start talking"}>
        <IconButton onClick={this.toggleTalking} aria-label={this.state.talking ? "Stop talking" : "Start talking"}>
            {this.state.talking ? <MicOffIcon /> : <MicIcon />}
        </IconButton>
    </Tooltip>
)}
{this.state.robot_config.robot_has_microphone && (
    <Tooltip title={this.state.listening ? "Stop listening" : "Listen to robot"}>
        <IconButton onClick={this.toggleListening} aria-label={this.state.listening ? "Stop listening" : "Listen to robot"}>
            {this.state.listening ? <VolumeOffIcon /> : <VolumeUpIcon />}
        </IconButton>
    </Tooltip>
)}
```

- [ ] **Step 6: Pass listening prop to VideoStreamControl**

Find the `<VideoStreamControl` element in `render()` and add the `listening` prop:

```jsx
<VideoStreamControl
    ref={this.videoStreamRef}
    updateFps={this.updateFps}
    sendWebRTCMessage={this.sendWebRTCMessage}
    talking={this.state.talking}
    listening={this.state.listening}
/>
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd react/pirobot && CI=true npm test -- --watchAll=false --testPathPattern=home.test
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
git add react/pirobot/src/home.js react/pirobot/src/home.test.js
git commit -m "feat: add listen-to-robot-mic toolbar button"
```

---

## Task 4: Feature 2 — VideoStreamControl.js listen prop

**Files:**
- Modify: `react/pirobot/src/VideoStreamControl.js`
- Test: `react/pirobot/src/VideoStreamControl.test.js`

- [ ] **Step 1: Add a test that the component renders without error with listening=true**

Append to `react/pirobot/src/VideoStreamControl.test.js`:

```js
test('renders without error when listening=true and talking=false', () => {
  expect(() => render(<VideoStreamControl {...baseProps} listening={true} />)).not.toThrow();
});
```

- [ ] **Step 2: Run test to verify it passes immediately**

```bash
cd react/pirobot && CI=true npm test -- --watchAll=false --testPathPattern=VideoStreamControl
```

Expected: all tests PASS (the new test verifies the prop is accepted without crash)

- [ ] **Step 3: Update componentDidUpdate in VideoStreamControl.js**

Replace the existing `componentDidUpdate`:

```js
componentDidUpdate(prevProps) {
    if (prevProps.talking !== this.props.talking) {
        this._startWebRTC(this.props.talking || false, this.props.listening || false);
    }
}
```

With:

```js
componentDidUpdate(prevProps) {
    const talkingChanged = prevProps.talking !== this.props.talking;
    const listeningChanged = prevProps.listening !== this.props.listening;
    if (talkingChanged) {
        this._startWebRTC(this.props.talking || false, this.props.listening || false);
    } else if (listeningChanged && !this.props.talking) {
        // Only restart for listening changes when not talking — robot audio
        // already flows during talk mode regardless of listening state.
        this._startWebRTC(false, this.props.listening || false);
    }
}
```

- [ ] **Step 4: Update _startWebRTC signature and audio transceiver logic**

Replace the `_startWebRTC` signature and its audio transceiver block.

Change the signature from:

```js
_startWebRTC = async (talking = false) => {
```

To:

```js
_startWebRTC = async (talking = false, listening = false) => {
```

Find the existing audio transceiver lines (inside `if (talking && this._localStream)`):

```js
if (talking && this._localStream) {
    pc.addTransceiver("audio", { direction: "recvonly" });
    const audioTrack = this._localStream.getAudioTracks()[0];
    const videoTrack = this._localStream.getVideoTracks()[0];
    if (audioTrack) pc.addTransceiver(audioTrack, { direction: "sendonly" });
    if (videoTrack) pc.addTransceiver(videoTrack, { direction: "sendonly" });
    if (this._pipRef.current) {
        this._pipRef.current.srcObject = this._localStream;
    }
}
```

Replace with:

```js
if ((talking || listening) ) {
    pc.addTransceiver("audio", { direction: "recvonly" });
}
if (talking && this._localStream) {
    const audioTrack = this._localStream.getAudioTracks()[0];
    const videoTrack = this._localStream.getVideoTracks()[0];
    if (audioTrack) pc.addTransceiver(audioTrack, { direction: "sendonly" });
    if (videoTrack) pc.addTransceiver(videoTrack, { direction: "sendonly" });
    if (this._pipRef.current) {
        this._pipRef.current.srcObject = this._localStream;
    }
}
```

- [ ] **Step 5: Pass listening in the offer message**

Find the offer message block:

```js
this.props.sendWebRTCMessage({
    action: "offer",
    sdp: pc.localDescription.sdp,
    type: "offer",
    talking: talking,
});
```

Replace with:

```js
this.props.sendWebRTCMessage({
    action: "offer",
    sdp: pc.localDescription.sdp,
    type: "offer",
    talking: talking,
    listening: listening,
});
```

- [ ] **Step 6: Update the _startWebRTC call in componentDidMount**

Replace:

```js
componentDidMount() {
    this._startWebRTC(this.props.talking || false);
}
```

With:

```js
componentDidMount() {
    this._startWebRTC(this.props.talking || false, this.props.listening || false);
}
```

Also update the call in `home.js` `ws.onopen` handler — find:

```js
this.videoStreamRef.current._startWebRTC(this.state.talking);
```

Replace with:

```js
this.videoStreamRef.current._startWebRTC(this.state.talking, this.state.listening);
```

- [ ] **Step 7: Run all frontend tests**

```bash
cd react/pirobot && CI=true npm test -- --watchAll=false
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
git add react/pirobot/src/VideoStreamControl.js react/pirobot/src/VideoStreamControl.test.js react/pirobot/src/home.js
git commit -m "feat: wire listening prop through VideoStreamControl WebRTC offer"
```

---

## Task 5: Feature 2 — Server-side listening support

**Files:**
- Modify: `server/webrtc.py`
- Modify: `server/webserver/session_manager.py`
- Test: `server/tests/test_webrtc.py`

- [ ] **Step 1: Write failing server test**

In `server/tests/test_webrtc.py`, find the `TestWebRTCSessionManager` class and append this test after `test_handle_offer_not_talking_skips_audio`:

```python
async def test_handle_offer_listening_creates_mic_track(self):
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
        await session.handle_offer(sdp="fake_sdp", talking=False, listening=True)

        MockMicTrack.assert_called_once()
        MockPlayer.assert_not_called()   # BrowserAudioPlayer only created when talking
        MockReceiver.assert_not_called() # BrowserVideoReceiver only created when talking
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd server && uv run python -m pytest tests/test_webrtc.py::TestWebRTCSessionManager::test_handle_offer_listening_creates_mic_track -v
```

Expected: FAIL — `handle_offer() got an unexpected keyword argument 'listening'`

- [ ] **Step 3: Update handle_offer in webrtc.py**

In `server/webrtc.py`, find:

```python
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
```

Replace with:

```python
async def handle_offer(self, sdp: str, talking: bool = False, listening: bool = False) -> None:
    await self._close_connection()

    self._pc = RTCPeerConnection()
    self._track = WebRTCTrack()
    self._pc.addTrack(self._track)

    if (talking or listening) and _sounddevice_available:
        self._mic_track = RobotMicTrack()
        self._pc.addTrack(self._mic_track)
    if talking and _sounddevice_available:
        self._audio_player = BrowserAudioPlayer()
        self._video_receiver = BrowserVideoReceiver()
```

- [ ] **Step 4: Run the new test to verify it passes**

```bash
cd server && uv run python -m pytest tests/test_webrtc.py::TestWebRTCSessionManager::test_handle_offer_listening_creates_mic_track -v
```

Expected: PASS

- [ ] **Step 5: Verify existing tests still pass**

```bash
cd server && uv run python -m pytest tests/test_webrtc.py::TestWebRTCSessionManager -v
```

Expected: all 3 session manager tests PASS

- [ ] **Step 6: Update session_manager.py to extract and forward listening**

In `server/webserver/session_manager.py`, find:

```python
talking = bool(msg.get("talking", False))
await self._webrtc.handle_offer(sdp, talking=talking)
```

Replace with:

```python
talking = bool(msg.get("talking", False))
listening = bool(msg.get("listening", False))
await self._webrtc.handle_offer(sdp, talking=talking, listening=listening)
```

- [ ] **Step 7: Run full server test suite**

```bash
cd server && uv run python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
git add server/webrtc.py server/webserver/session_manager.py server/tests/test_webrtc.py
git commit -m "feat: add listening mode to server WebRTC offer handler"
```

---

## Task 6: Full verification

- [ ] **Step 1: Run full frontend test suite**

```bash
cd react/pirobot && CI=true npm test -- --watchAll=false
```

Expected: all tests PASS

- [ ] **Step 2: Run full server test suite**

```bash
cd server && uv run python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 3: Build frontend**

```bash
cd react/pirobot && npm run build
```

Expected: build succeeds with no errors

- [ ] **Step 4: Final commit if any loose files**

```bash
git status
# If any modified files remain unstaged, stage and commit them
```
