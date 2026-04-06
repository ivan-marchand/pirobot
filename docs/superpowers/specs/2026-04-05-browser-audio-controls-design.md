# Browser Audio Controls Design

**Date:** 2026-04-05
**Branch:** feat/duplex-videochat

## Overview

Two related features for the browser control interface:

1. **In-call controls** — mute mic and disable camera while in a talk session, via overlay buttons on the PiP.
2. **Listen mode** — receive robot mic audio without entering a full talk session; off by default, toggled from the toolbar.

---

## Feature 1: In-Call Mute & Camera-Off

### Placement

Overlay buttons on the PiP (user's camera preview, bottom-right corner of the video area). Only visible when `talking=true`.

### Behaviour

- **Mute** — toggles `audioTrack.enabled` on `_localStream`. Sends silence to the robot without stopping the track or renegotiating. Icon: `MicIcon` / `MicOffIcon`.
- **Camera off** — toggles `videoTrack.enabled` on `_localStream`. Sends black frames to the robot without stopping the track. Icon: `VideocamIcon` / `VideocamOffIcon`.
- When camera is off, the PiP shows a dark placeholder with a centered `VideocamOffIcon` instead of the live preview.
- Both states reset to `false` when `_startWebRTC` is called (i.e. when a new session starts).

### Implementation

**`VideoStreamControl.js` only** — no server changes, no `home.js` changes.

- Add `muted: false` and `cameraOff: false` to component state.
- Add `toggleMuted` and `toggleCamera` handlers using optional chaining (`_localStream?.getAudioTracks()[0]`) so they are safe before a stream exists.
- The PiP `<video>` element stays always in the DOM when `talking=true` (so `_pipRef` and `srcObject` remain valid). Hidden via `display: none` when `cameraOff=true`.
- A `position: absolute` placeholder div overlays the video when `cameraOff=true`.
- Two `IconButton` (size `small`) in a semi-transparent bar at the bottom of the PiP container.

### PiP structure (when `talking=true`)

```
┌─────────────────────┐
│                     │  ← PiP container (position: absolute, 120×90)
│  [video or icon]    │
│ ┌─────────────────┐ │
│ │  🎙️  📷         │ │  ← semi-transparent overlay bar at bottom
│ └─────────────────┘ │
└─────────────────────┘
```

---

## Feature 2: Listen Mode

### Overview

A "listen" button in the toolbar lets the user receive audio from the robot's microphone without entering a full talk session (no browser mic/camera sent). Off by default.

### Placement

Toolbar, next to the talk (mic) button. Gated on `robot_has_microphone` — same condition as the talk button. Icon: `VolumeUpIcon` (inactive) / `VolumeOffIcon` (active — currently listening).

### Behaviour

- Toggling listen restarts the WebRTC connection (same pattern as toggling `talking`).
- When `listening=true` and `talking=false`: adds an `audio recvonly` transceiver; sends `listening: true` in the offer. Server adds `RobotMicTrack`.
- When `listening=true` and `talking` becomes `true`: talk mode already includes robot audio (`audio recvonly` + `RobotMicTrack`), so `listening` is effectively absorbed. `listening` state is not reset — when talk ends, it remains.
- When `listening` changes while `talking=true`: no renegotiation needed (robot audio already flowing); `_startWebRTC` is not called.
- Robot mic only runs when `talking || listening` — never on by default.
- Not available on robots without a microphone (`robot_has_microphone: false`).

### Data flow

```
Browser                         Server
  |                               |
  |-- offer (listening=true) ---->|
  |   audio recvonly transceiver  |  adds RobotMicTrack
  |<-- answer + RobotMicTrack ----|
  |                               |
  | <audio> element plays         |
  | robot mic audio               |
```

### Implementation

**`home.js`:**
- Add `listening: false` to state.
- Add `toggleListening` method.
- Pass `listening={this.state.listening}` prop to `VideoStreamControl`.
- Render listen button in toolbar, gated on `robot_has_microphone`, next to the talk button.

**`VideoStreamControl.js`:**
- Accept `listening` prop.
- `componentDidUpdate`: restart WebRTC when `listening` changes AND `!this.props.talking` (no restart needed if talking, robot audio already flowing).
- `_startWebRTC(talking, listening)`: add `audio recvonly` transceiver when `talking || listening`.
- Include `listening` in the offer message to the server.

**`server/webrtc.py`:**
- Offer handler: add `RobotMicTrack` when `talking or listening` (currently: only when `talking`).
- `listening` defaults to `False` for backwards compatibility.

---

## Tests

**`VideoStreamControl.test.js`** (new):
- Mute and camera buttons render when `talking=true`.
- Clicking mute toggles between `MicIcon` and `MicOffIcon`.
- Clicking camera-off shows the placeholder.

**`home.test.js`** (new):
- Listen button renders when `robot_has_microphone=true`.
- Listen button does not render when `robot_has_microphone=false`.
- Clicking listen toggles state.

---

## Out of Scope

- Volume control for robot audio.
- Visual indicator to the robot that browser is listening (no server-side state change for listen mode).
- Persisting mute/listen state across sessions or page reloads.
