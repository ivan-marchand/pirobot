# PiRobot
https://pirobot.net/

Web-controlled robot platform for Raspberry Pi. Control interface runs in a browser; hardware is driven by a Python async server communicating with a Raspberry Pi Pico over UART.

## Raspberry Pi Install

### Prerequisites

```bash
sudo apt update
sudo apt install git python3-pip python3-picamera2 espeak
pip install uv
```

> `espeak` is optional — text-to-speech is silently disabled if absent.

### Install

```bash
mkdir git && cd git
git clone https://github.com/ivan-marchand/pirobot.git
cd pirobot/server
./install.sh
```

`install.sh` will:
- Create a uv virtualenv with system-site-packages (required for `picamera2`)
- Build a self-contained `pirobotd` binary with PyInstaller
- Install it to `/usr/local/bin/pirobotd`
- Copy config/assets to `/etc/pirobot/`
- Copy the React build to `/var/www/`
- Install and enable the `pirobot` systemd service

### Service management

```bash
sudo systemctl status pirobot
sudo journalctl -u pirobot -f
sudo systemctl restart pirobot
```

## Development

### Server

```bash
cd server
uv sync
uv run python manage.py runserver              # port 8080
uv run python manage.py -c pirobot runserver   # with specific robot config
```

### Frontend

```bash
cd react/pirobot
npm install
npm start       # dev server on port 3000
npm run build
```

## Configuration

```bash
uv run python manage.py configuration get
uv run python manage.py configuration get <key>
uv run python manage.py configuration update <key> <value>
```

Robot config files live in `server/config/*.robot.json` and support inheritance via `"include"`. Runtime config is stored at `~/.pirobot/pirobot.config`.
