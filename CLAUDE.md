# PiRobot

Web-controlled robot platform for Raspberry Pi. Control interface runs in a browser; hardware is driven by a Python async server communicating with a Raspberry Pi Pico over UART.

## Architecture

```
react/pirobot/   React frontend (Material-UI, WebSocket client)
server/          Python backend (aiohttp, async/await)
pico/            MicroPython firmware for Raspberry Pi Pico
```

**Communication flow:**
- Control: Browser ↔ WebSocket (`/ws/robot`) ↔ Python server ↔ UART ↔ Pico ↔ motors/servos/sensors
- Video: Browser ↔ WebRTC (signalled via `/ws/robot`) ↔ Python server ↔ camera

**Message protocol:** JSON with `type`, `action`, `args` fields inbound; `topic`, `message` fields outbound.

## Server

**Stack:** Python 3.9, aiohttp, SQLAlchemy (SQLite), OpenCV, pygame, pyserial, aiortc

**Entry point:** `server/manage.py`

```bash
cd server
uv sync                                        # install deps
uv run python manage.py runserver              # start server (port 8080)
uv run python manage.py -c pirobot runserver   # with specific robot config
```

**Config management:**
```bash
uv run python manage.py configuration get
uv run python manage.py configuration get <key>
uv run python manage.py configuration update <key> <value>
```

**Key files:**
- `server/server.py` — main Server class
- `server/webserver/app.py` — aiohttp routes and WebSocket handlers
- `server/webrtc.py` — WebRTC video streaming (aiortc)
- `server/handlers/` — one handler per subsystem (drive, arm, camera, sfx, talk, light, battery, lcd, face_detection, qr_code, configuration)
- `server/models.py` — config/DB layer (SQLite at `~/.pirobot/db.sqlite3`)
- `server/arm.py` — robot arm servo control
- `server/camera.py` — camera and vision subsystem
- `server/uart.py` — UART comms with Pico (auto-reconnect)
- `server/motor/motor.py` — motor movement control
- `server/config/` — JSON robot definitions (default, pirobot, picaterpillar, turtle)

**Robot configs** live in `server/config/*.robot.json` and support inheritance via `"include"`. Runtime config is stored at `~/.pirobot/pirobot.config`.

## Frontend

**Stack:** React 18, Material-UI, react-joystick-component, react-router-dom 6

```bash
cd react/pirobot
npm install
npm start    # dev server on port 3000
npm run build
```

**Key files:**
- `src/home.js` — main control interface
- `src/ArmControl.js` — arm manipulation UI
- `src/VideoStreamControl.js` — WebRTC video feed
- `src/DirectionCross.js` — directional input widget

## Pico Firmware

MicroPython at `pico/main.py`. Communicates over UART at 115200 baud. Deploy by copying to the Pico.

## Production Deployment

```bash
cd server
./install.sh          # builds PyInstaller binary, installs systemd service
```

Runs as `www-data` user. Default ports: 8080 (web).

`install.sh` requires `uv` to be installed (`pip install uv`). It resolves the `uv` path automatically so it works when run via SSH without a login shell.

## Hardware Capabilities (all configurable per robot JSON)

- Drive motors
- Robot arm — 4 servos: shoulder, forearm, wrist, claw
- Front/back cameras
- RGB lighting
- 2-inch LCD screen
- Speaker (text-to-speech via pyttsx3/espeak, SFX via pygame)
- Ultrasonic sensors (front/sides)
- Battery voltage monitoring

## Development Notes

- Use `fake-rpi` (already in pyproject.toml) to mock GPIO/hardware on non-Pi machines
- Handler routing is defined in each handler's `register` method via the base class in `server/handlers/base.py`
- The server is fully async; avoid blocking calls in handlers
- `picamera2` and `libcamera` are apt-only packages (not on PyPI). They are soft-imported with `try/except` so the server starts on macOS. On Pi they are accessed via the `--system-site-packages` venv.
- `pyttsx3` init is wrapped in try/except; `espeak` may not be installed and is not required
- aiohttp WebSocket handlers **must** `return ws` at the end — returning `None` causes a 500 error

## Platform-Specific Dependencies (pyproject.toml)

These are conditional on `platform_machine == 'aarch64'` (Raspberry Pi 64-bit):

| Package | Reason |
|---|---|
| `aiortc>=1.9.0,<1.10` | Bullseye ships ffmpeg 4; aiortc 1.10+ requires ffmpeg 7 |
| `RPi.GPIO` | GPIO hardware access |
| `spidev` | SPI bus for LED/LCD hardware |
| `numpy<2` | picamera2/simplejpeg are compiled against numpy 1.x ABI |
| `setuptools<65` | PyInstaller's `pyi_rth_pkgres` hook crashes with setuptools 65+ (requires `jaraco` which isn't a standalone pip package) |

## PyInstaller Notes

- Use `--hidden-import picamera2 --hidden-import libcamera` — **not** `--collect-all`. `--collect-all` uses `importlib.metadata` to find dist-info, which doesn't exist for apt packages, causing `pyi_rth_pkgres` to crash with `InvalidVersion`.
- The `--system-site-packages` venv lets PyInstaller find and bundle apt packages during analysis.
- `uv` is not in PATH when `install.sh` runs via SSH non-login shell; the script resolves it via `$(which uv || echo $HOME/.local/bin/uv)`.

## Camera Notes

- USB cameras on Linux require `cv2.VideoCapture(index, cv2.CAP_V4L2)` with `MJPG` format — the default backend may silently fail.
- Probe camera index 0 before 1. On Pi, index 1 is often the metadata/ISP device, not a capture device.
- Camera config changes (resolution, FPS) restart the capture task in-place — no server restart needed.
- `back_capturing_device: "none"` means no back camera; no PiP overlay is shown (this is correct behavior).
