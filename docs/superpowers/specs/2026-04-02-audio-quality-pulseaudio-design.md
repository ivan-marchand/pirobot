# Audio Quality & Echo Cancellation — Design

**Date:** 2026-04-02
**Branch:** feat/duplex-videochat

## Problem

Two distinct audio issues affect the robot's duplex video chat:

1. **Low-pitch distortion** — audio from the browser plays out of the robot speaker at a noticeably lower pitch, making speech barely intelligible. The pitch is wrong from the very start of the call (constant, not drifting), which points to a sample rate or format mismatch rather than a codec quality issue.

2. **Echo** — the robot's microphone picks up the speaker output and sends it back to the browser. There is no acoustic echo cancellation (AEC) on the robot side.

Hardware is not the issue: `aplay` of a local WAV and `espeak` both sound correct on the robot.

## Goals

- Fix the low-pitch distortion so speech is intelligible at natural pitch
- Eliminate echo heard in the browser during a talk session
- Require no changes to the Python audio pipeline code

## Architecture

PulseAudio runs as a system daemon between the application layer and ALSA. It handles resampling correctly (fixing pitch) and runs Chromium's WebRTC AEC engine to subtract the speaker signal from the microphone signal (fixing echo).

```
Before:
  aplay (48kHz) ──→ ALSA/bcm2835 ──→ speaker      (possible bad resampling)
  sounddevice ←── ALSA/bcm2835 ←── mic             (no echo cancellation)

After:
  aplay ──→ ALSA/PulseAudio plugin ──→ PulseAudio ──→ [echo-cancel sink] ──→ bcm2835 ──→ speaker
  sounddevice ←── ALSA/PulseAudio plugin ←── PulseAudio ←── [echo-cancel source] ←── mic
                                                                    ↑ reference (speaker signal)
```

`aplay` and `sounddevice` route through PulseAudio transparently via the ALSA PulseAudio plugin — no Python code changes required.

## Phase 1: Diagnosis

Before setting up PulseAudio, confirm the root cause of the low pitch.

**Log line** (added to `BrowserAudioPlayer._receive` on first frame):
```python
logger.info(
    f"BrowserAudioPlayer: first frame — format={frame.format.name}, "
    f"sample_rate={frame.sample_rate}, samples={frame.samples}, "
    f"channels={len(frame.layout.channels)}, "
    f"ndarray shape={frame.to_ndarray().shape}, dtype={frame.to_ndarray().dtype}"
)
```

**ALSA tone test** (run on Pi):
```bash
python3 -c "
import numpy as np, sys
rate = 48000
t = np.linspace(0, 1, rate)
wave = (np.sin(2*np.pi*440*t) * 32767).astype(np.int16)
sys.stdout.buffer.write(wave.tobytes())
" | aplay -f S16_LE -r 48000 -c 1 -t raw
```

If the tone sounds lower than A4, bcm2835/ALSA is resampling incorrectly — PulseAudio fixes it.
If the tone sounds correct, the bug is in the format conversion and the log line will show the mismatch.

## Phase 2: PulseAudio Setup

### Packages

```bash
sudo apt install pulseaudio pulseaudio-utils libasound2-plugins
```

`libasound2-plugins` provides the ALSA PulseAudio plugin so that `aplay`, `sounddevice`, and other ALSA apps route through PulseAudio automatically.

### PulseAudio System Config — `/etc/pulse/system.pa`

Replaces the default per-user session config. Runs a single system daemon accessible to all users including `www-data`.

```
load-module module-native-protocol-unix auth-anonymous=1
load-module module-alsa-sink device=hw:0,0
load-module module-alsa-source device=hw:0,0
load-module module-echo-cancel aec_method=webrtc \
    source_master=alsa_input.hw_0_0 \
    sink_master=alsa_output.hw_0_0 \
    source_name=echocancel \
    sink_name=echocancel
set-default-source echocancel
set-default-sink echocancel
```

`aec_method=webrtc` uses Chromium's WebRTC AEC engine, the same engine the browser uses for its own microphone.

### ALSA Default — `/etc/asound.conf`

Routes all ALSA applications through PulseAudio:

```
pcm.!default {
    type pulse
}
ctl.!default {
    type pulse
}
```

### Permissions

```bash
sudo adduser www-data pulse-access
```

The robot server runs as `www-data` and needs access to the PulseAudio Unix socket. The service must be restarted after adding this group membership.

### Systemd

```bash
sudo systemctl enable pulseaudio
sudo systemctl start pulseaudio
```

PulseAudio must be configured for system mode (`--system` flag) in its systemd unit.

### Verification (added to `install.sh`)

After installation, verify PulseAudio is reachable and echo-cancel is loaded:

```bash
pactl info > /dev/null && echo "PulseAudio: OK" || echo "PulseAudio: WARN — daemon not reachable"
pactl list modules short | grep -q module-echo-cancel && echo "AEC: OK" || echo "AEC: WARN — echo-cancel not loaded"
```

## Error Handling & Rollback

| Failure | Behaviour |
|---|---|
| PulseAudio daemon not running | `aplay`/sounddevice fall back to direct ALSA (pitch issue returns, no AEC, but robot still works) |
| `module-echo-cancel` fails to load | Audio works without AEC; install.sh prints a warning |
| `www-data` lacks socket access | Falls back to direct ALSA; fixed by restarting the service after adding to `pulse-access` group |
| Full rollback needed | Remove `/etc/asound.conf` — direct ALSA restored immediately, no reboot |

## Code Changes

None required to `webrtc.py`. The existing `aplay` invocation and `sounddevice` capture both work as-is once ALSA defaults to PulseAudio.

The only code change is the diagnostic log line in `BrowserAudioPlayer._receive` (Phase 1), which can be removed after the root cause is confirmed.

## Testing

1. Run the ALSA tone test — confirm A4 pitch before and after PulseAudio setup
2. Start a talk session — confirm speech is intelligible at natural pitch
3. Speak into the browser mic — confirm no echo heard in the browser
4. Run `pactl list modules short` — confirm `module-echo-cancel` is loaded
5. Stop the talk session — confirm video continues (regression check)
6. Restart the robot service — confirm PulseAudio persists across restarts
