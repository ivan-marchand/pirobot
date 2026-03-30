# Talk Feature Design

**Date:** 2026-03-29
**Status:** Approved

## Overview

Full-duplex two-way communication between the browser client and the robot. When the user starts talking:

- The browser microphone is streamed to the robot's speaker
- The robot's microphone is streamed back to the browser
- The browser webcam is streamed to the robot's LCD (full-screen, 240×320)
- The robot's camera continues streaming to the browser (same as today)

The feature is called "talking" (not "call"). It is gated behind a `robot_has_microphone` capability flag.

## Architecture

### Connection Strategy

A single `RTCPeerConnection` is used at all times (same as today for video-only). When the user starts or stops talking, the connection is **closed and reopened** with the appropriate set of tracks. The robot camera video briefly drops (~1 second) during the transition — this is accepted behavior.

**Video-only mode (today's behavior):**
- Browser recvonly video transceiver (robot camera → browser)

**Talk mode:**
- Browser recvonly video transceiver (robot camera → browser)
- Browser recvonly audio transceiver (robot mic → browser)
- Browser sendonly audio transceiver (browser mic → robot speaker)
- Browser sendonly video transceiver (browser webcam → robot LCD)

The offer message gains a `talking: bool` field that tells the server which mode to set up.

## Server-side Changes

**File: `server/webrtc.py`**

Three new classes:

- **`RobotMicTrack(AudioStreamTrack)`** — captures audio from the Pi microphone at 48 kHz mono using `sounddevice`. Starts the `sounddevice` input stream when the track is first consumed; stops it when the WebRTC connection closes.

- **`BrowserAudioPlayer`** — consumes incoming `AudioFrame` objects from the browser mic track and plays them through the Pi speaker via `sounddevice` output in a background async task.

- **`BrowserVideoReceiver`** — consumes incoming video frames from the browser webcam track. Converts each frame to RGB (numpy array) and calls `LcdHandler.display_frame(frame)` to render full-screen on the LCD.

**`WebRTCSessionManager` changes:**
- Reads `talking` field from the offer message (defaults to `false`)
- When `talking=true`: adds `RobotMicTrack` to the peer connection; registers `BrowserAudioPlayer` and `BrowserVideoReceiver` as consumers on the incoming tracks
- When `talking=false`: video-only setup as today
- On connection close: stops `RobotMicTrack` and `BrowserAudioPlayer` if active; notifies `LcdHandler` to resume normal display

**File: `server/handlers/lcd.py`**

- New method `display_frame(frame: np.ndarray)` — renders a numpy RGB frame full-screen (scaled to 240×320), bypassing normal text/image rendering
- New method `stop_video()` — resumes normal LCD rendering
- Called by `BrowserVideoReceiver` on each frame, and on talk end respectively

**New config key:**

```json
"robot_has_microphone": {
  "type": "bool",
  "default": false,
  "export": true,
  "need_setup": true,
  "category": "capability"
}
```

## Client-side Changes

**File: `react/pirobot/src/VideoStreamControl.js`**

- New prop: `talking` (bool)
- `_startWebRTC(talking)`:
  - When `talking=true`: calls `getUserMedia({audio: true, video: true})`, adds a `sendonly` audio transceiver and a `sendonly` video transceiver before creating the offer. Sends `{..., talking: true}` in the signalling message.
  - When `talking=false`: same as today, sends `talking: false`
- On remote track received: audio track is set as `srcObject` on a hidden `<audio autoPlay>` element
- **PiP overlay**: when `talking`, a small `<video>` element positioned in the bottom-right corner of the video container is fed the local `getUserMedia` video stream (browser webcam preview)
- On stop: local media tracks are stopped before the connection is closed

**File: `react/pirobot/src/home.js`**

- New state: `talking` (bool, default `false`)
- Toolbar renders a mic icon button when `capabilities.robot_has_microphone` is true
- Clicking toggles `talking`, which is passed as a prop to `VideoStreamControl`
- `VideoStreamControl` watches the `talking` prop and triggers a connection restart when it changes

## Data Flow

```
Browser                          Server (Pi)
──────                           ──────────
[Mic] ──sendonly audio──────►  BrowserAudioPlayer ──► sounddevice out ──► [Speaker]
[Webcam] ──sendonly video────►  BrowserVideoReceiver ──► LcdHandler ──► [LCD 240×320]
         ◄──recvonly audio────  RobotMicTrack ◄── sounddevice in ◄── [Microphone]
         ◄──recvonly video────  WebRTCTrack ◄── Camera (unchanged)
```

## Error Handling

- If `getUserMedia` is denied: show a snackbar error, do not start talking
- If `sounddevice` is not available on the Pi: `RobotMicTrack` is not added; one-way audio still works (browser mic → Pi speaker)
- If the LCD handler is not active (`robot_has_screen=false`): `BrowserVideoReceiver` is a no-op

## Dependencies

- `sounddevice` — added to `pyproject.toml` (Pi only, `platform_machine == 'aarch64'`)
- No new frontend dependencies

## Out of Scope

- Push-to-talk mode
- Mute button (browser's native WebRTC controls handle this; can be added later)
- Multiple simultaneous talkers
- Audio quality tuning / echo cancellation (browser WebRTC stack handles AEC natively)
