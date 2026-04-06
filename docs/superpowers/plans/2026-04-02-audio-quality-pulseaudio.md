# Audio Quality & Echo Cancellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix low-pitch audio distortion from the robot speaker and eliminate echo heard in the browser by routing audio through PulseAudio with Chromium's WebRTC echo cancellation module.

**Architecture:** PulseAudio runs as a system daemon with `module-echo-cancel` (AEC method: webrtc), sitting between applications and ALSA. `aplay` and `sounddevice` route through PulseAudio transparently via the ALSA PulseAudio plugin — no changes to the Python audio pipeline. A one-time diagnostic log line is added to confirm the PCM format before deploying PulseAudio.

**Tech Stack:** PulseAudio (`module-echo-cancel`, `module-alsa-sink/source`), `libasound2-plugins` (ALSA→PulseAudio bridge), Python `unittest`/`IsolatedAsyncioTestCase`, `assertLogs`

---

### Task 1: Add first-frame diagnostic log + fix stale BrowserAudioPlayer test

The existing `test_stop_cancels_task` patches `webrtc.sd` (sounddevice), but `BrowserAudioPlayer` no longer uses sounddevice — it spawns an `aplay` subprocess. This test is broken. Fix it and add a test for the new diagnostic log line.

**Files:**
- Modify: `server/webrtc.py`
- Modify: `server/tests/test_webrtc.py`

- [ ] **Step 1: Write the failing first-frame log test**

Open `server/tests/test_webrtc.py`. Replace the entire `TestBrowserAudioPlayer` class with:

```python
class TestBrowserAudioPlayer(unittest.IsolatedAsyncioTestCase):

    def _make_mock_proc(self):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.close = MagicMock()
        mock_proc.terminate = MagicMock()
        mock_proc.wait = AsyncMock()
        return mock_proc

    async def test_stop_cancels_task(self):
        with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=self._make_mock_proc())):
            from webrtc import BrowserAudioPlayer
            player = BrowserAudioPlayer()
            mock_track = MagicMock()
            mock_track.recv = AsyncMock(side_effect=asyncio.CancelledError())
            player.start(mock_track)
            self.assertIsNotNone(player._task)
            await asyncio.sleep(0)
            player.stop()
            self.assertIsNone(player._task)

    async def test_first_frame_logs_format_info(self):
        import av
        call_count = 0

        frame = av.AudioFrame(format='s16', layout='mono', samples=960)
        frame.sample_rate = 48000
        frame.pts = 0

        async def recv_impl():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return frame
            await asyncio.sleep(10)  # block so the task doesn't race past the assert

        mock_track = MagicMock()
        mock_track.recv = recv_impl

        with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=self._make_mock_proc())), \
             self.assertLogs('webrtc', level='INFO') as captured:
            from webrtc import BrowserAudioPlayer
            player = BrowserAudioPlayer()
            player.start(mock_track)
            await asyncio.sleep(0.05)
            player.stop()
            await asyncio.sleep(0.05)

        self.assertTrue(
            any('first frame' in msg for msg in captured.output),
            f"Expected 'first frame' in log output, got: {captured.output}"
        )
```

- [ ] **Step 2: Run the new test to verify it fails**

```bash
cd server
uv run python -m pytest tests/test_webrtc.py::TestBrowserAudioPlayer -v
```

Expected: `test_first_frame_logs_format_info` FAIL (no log line exists yet); `test_stop_cancels_task` PASS (the mock fix is enough).

- [ ] **Step 3: Add the diagnostic log line to `BrowserAudioPlayer._receive`**

In `server/webrtc.py`, find `BrowserAudioPlayer._receive`. Add a `_first_frame_logged` flag before the `while True:` loop and log on first frame. The method should look like this (only the additions are marked with `# <-- new`):

```python
    async def _receive(self, track) -> None:
        import time
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "aplay", "-f", "S16_LE", "-r", "48000", "-c", "1", "-t", "raw",
                "-B", "200000",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            logger.info("BrowserAudioPlayer: aplay started")
            start_time: Optional[float] = None
            bytes_written = 0
            _first_frame_logged = False  # <-- new
            while True:
                try:
                    frame = await track.recv()
                    pcm_bytes = frame.to_ndarray().flatten().astype(np.int16).tobytes()

                    if not _first_frame_logged:  # <-- new
                        logger.info(
                            f"BrowserAudioPlayer: first frame — "
                            f"format={frame.format.name}, "
                            f"sample_rate={frame.sample_rate}, "
                            f"samples={frame.samples}, "
                            f"channels={len(frame.layout.channels)}, "
                            f"ndarray shape={frame.to_ndarray().shape}, "
                            f"dtype={frame.to_ndarray().dtype}"
                        )
                        _first_frame_logged = True  # <-- new

                    now = time.monotonic()
                    if start_time is None:
                        start_time = now

                    elapsed = now - start_time
                    bytes_played = max(0.0, elapsed - self._APLAY_BUFFER_SEC) * self._BYTES_PER_SEC
                    buffer_depth_sec = (bytes_written - bytes_played) / self._BYTES_PER_SEC

                    if buffer_depth_sec > self._MAX_AHEAD_SEC:
                        continue

                    proc.stdin.write(pcm_bytes)
                    bytes_written += len(pcm_bytes)
                except asyncio.CancelledError:
                    raise
                except MediaStreamError:
                    break
                except Exception as exc:
                    logger.warning(f"BrowserAudioPlayer frame error: {type(exc).__name__}: {exc}")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"BrowserAudioPlayer: failed to start aplay: {exc}")
        finally:
            if proc is not None:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except Exception:
                    pass
```

- [ ] **Step 4: Run the tests to verify they all pass**

```bash
cd server
uv run python -m pytest tests/test_webrtc.py::TestBrowserAudioPlayer -v
```

Expected: both tests PASS.

- [ ] **Step 5: Run the full test suite**

```bash
cd server
uv run python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
cd server
git add webrtc.py tests/test_webrtc.py
git commit -m "feat(audio): add first-frame diagnostic log, fix stale BrowserAudioPlayer test"
```

---

### Task 2: Create PulseAudio and ALSA config template files

These files are deployed by `install.sh` to the correct system paths on the Pi. Keeping them in the repo makes the setup reproducible.

**Files:**
- Create: `server/config/audio/pulse-system.pa`
- Create: `server/config/audio/asound.conf`
- Create: `server/config/audio/pulseaudio.service`

- [ ] **Step 1: Create the PulseAudio system config**

Create `server/config/audio/pulse-system.pa`:

```
# PulseAudio system-mode config for PiRobot
# Deployed to /etc/pulse/system.pa by install.sh
#
# module-echo-cancel uses Chromium's WebRTC AEC engine to subtract the
# speaker signal from the robot microphone, preventing echo in the browser.

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

- [ ] **Step 2: Create the ALSA default config**

Create `server/config/audio/asound.conf`:

```
# Route all ALSA applications through PulseAudio.
# Deployed to /etc/asound.conf by install.sh.
# Remove this file to revert to direct ALSA.

pcm.!default {
    type pulse
}
ctl.!default {
    type pulse
}
```

- [ ] **Step 3: Create the systemd unit file for system-mode PulseAudio**

Create `server/config/audio/pulseaudio.service`:

```ini
[Unit]
Description=PulseAudio Sound System (system mode for PiRobot)
After=sound.target

[Service]
Type=notify
ExecStart=/usr/bin/pulseaudio --system --disallow-exit --disallow-module-loading=0 --daemonize=no --log-target=journal
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: Commit**

```bash
git add server/config/audio/
git commit -m "feat(audio): add PulseAudio and ALSA config templates"
```

---

### Task 3: Update install.sh with PulseAudio setup

**Files:**
- Modify: `server/install.sh`

- [ ] **Step 1: Add PulseAudio setup block to install.sh**

Open `server/install.sh`. Add the following block **before** the final `sudo systemctl restart pirobot` line:

```bash
# --- PulseAudio setup ---
echo "Installing PulseAudio..."
sudo apt-get install -y pulseaudio pulseaudio-utils libasound2-plugins

echo "Deploying PulseAudio config..."
sudo cp config/audio/pulse-system.pa /etc/pulse/system.pa
sudo cp config/audio/asound.conf /etc/asound.conf
sudo cp config/audio/pulseaudio.service /etc/systemd/system/pulseaudio.service

echo "Configuring PulseAudio permissions..."
sudo adduser www-data pulse-access

echo "Starting PulseAudio system service..."
sudo systemctl daemon-reload
sudo systemctl enable pulseaudio.service
sudo systemctl restart pulseaudio.service

echo "Verifying PulseAudio..."
sleep 2  # give the daemon a moment to start
if pactl info > /dev/null 2>&1; then
    echo "  PulseAudio: OK"
else
    echo "  WARNING: PulseAudio daemon not reachable — check: journalctl -u pulseaudio"
fi
if pactl list modules short 2>/dev/null | grep -q module-echo-cancel; then
    echo "  Echo cancellation (webrtc): OK"
else
    echo "  WARNING: module-echo-cancel not loaded — check /etc/pulse/system.pa"
    echo "  If webrtc AEC is unavailable on this build, edit pulse-system.pa:"
    echo "  change aec_method=webrtc to aec_method=speex and run install.sh again"
fi
# --- end PulseAudio setup ---
```

- [ ] **Step 2: Verify install.sh syntax**

```bash
bash -n server/install.sh
```

Expected: no output (no syntax errors).

- [ ] **Step 3: Commit**

```bash
git add server/install.sh
git commit -m "feat(audio): add PulseAudio AEC setup to install.sh"
```

---

### Task 4: Pi deployment and manual verification

This task runs on the Pi. No code changes — pure verification.

**Pre-condition:** The robot is running the latest build (from a `./install.sh` run that did NOT yet include the PulseAudio block, or roll back `/etc/asound.conf` and `/etc/pulse/system.pa` if already deployed).

- [ ] **Step 1: Run the ALSA tone test (before PulseAudio) to confirm the pitch bug**

SSH into the Pi and run:

```bash
python3 -c "
import numpy as np, sys
rate = 48000
t = np.linspace(0, 1, rate)
wave = (np.sin(2*np.pi*440*t) * 32767).astype(np.int16)
sys.stdout.buffer.write(wave.tobytes())
" | aplay -f S16_LE -r 48000 -c 1 -t raw
```

A correctly-playing 440 Hz tone sounds like a standard pitch A4 (the tuning note for orchestras). If it sounds lower, the bcm2835 ALSA driver is the culprit and PulseAudio will fix it. Note what you hear.

- [ ] **Step 2: Deploy and start a talk session — read the first-frame log line**

On the Pi, tail the robot log during a talk session:

```bash
journalctl -u pirobotd -f | grep "first frame"
```

Start a talk session from the browser. The log line should appear, e.g.:

```
BrowserAudioPlayer: first frame — format=s16, sample_rate=48000, samples=1920, channels=1, ndarray shape=(1, 1920), dtype=int16
```

If `format` is not `s16` or `sample_rate` is not `48000`, there is a format conversion bug — stop here and fix the conversion before proceeding with PulseAudio.

- [ ] **Step 3: Run install.sh to deploy PulseAudio**

From the server directory on the Pi:

```bash
./install.sh
```

Watch for the PulseAudio section output. Expected:

```
Installing PulseAudio...
Deploying PulseAudio config...
Configuring PulseAudio permissions...
Starting PulseAudio system service...
Verifying PulseAudio...
  PulseAudio: OK
  Echo cancellation (webrtc): OK
```

If `Echo cancellation (webrtc): OK` does not appear, edit `/etc/pulse/system.pa` on the Pi and change `aec_method=webrtc` to `aec_method=speex`, then:

```bash
sudo systemctl restart pulseaudio
pactl list modules short | grep echo-cancel
```

- [ ] **Step 4: Run the ALSA tone test again (after PulseAudio)**

```bash
python3 -c "
import numpy as np, sys
rate = 48000
t = np.linspace(0, 1, rate)
wave = (np.sin(2*np.pi*440*t) * 32767).astype(np.int16)
sys.stdout.buffer.write(wave.tobytes())
" | aplay -f S16_LE -r 48000 -c 1 -t raw
```

Expected: the tone now sounds at the correct A4 pitch (or noticeably closer to it than before).

- [ ] **Step 5: Test a talk session end-to-end**

Start a talk session from the browser. Verify:

1. **Pitch**: your voice sounds natural, not low-pitched
2. **Echo**: you do not hear your own voice echoed back in the browser
3. **Video**: the robot camera feed continues playing normally
4. **Regression**: stopping the talk session and restarting it works without freezing

- [ ] **Step 6: Verify PulseAudio survives a robot service restart**

```bash
sudo systemctl restart pirobotd
# wait 5 seconds
pactl info
```

Expected: `pactl info` still returns PulseAudio server info (PulseAudio is independent of the robot service).
