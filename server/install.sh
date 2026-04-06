APP_NAME=pirobot
DAEMON_NAME=pirobotd

# Resolve uv path (not always in PATH when run via SSH)
UV=$(which uv 2>/dev/null || echo "$HOME/.local/bin/uv")

# Ensure venv has access to system packages (needed for picamera2, RPi.GPIO etc.)
$UV venv --system-site-packages
$UV sync

$UV run pyinstaller manage.py $(ls handlers/* | grep -v __init__.py | grep -v base.py | grep -v __pycache__ | grep -v .pyc | sed -e 's/handlers\/\(\w\+\).py/ --hidden-import  handlers.\1/g') --collect-all cv2 --hidden-import picamera2 --hidden-import libcamera -F -n $DAEMON_NAME

sudo systemctl stop pirobot 2>/dev/null || true
sudo cp dist/$DAEMON_NAME /usr/local/bin/
sudo mkdir -p /etc/$APP_NAME
sudo cp -rf config /etc/$APP_NAME/
sudo cp -rf assets /etc/$APP_NAME/
sudo cp pirobot.config /etc/$APP_NAME/

sudo adduser www-data spi
sudo adduser www-data gpio
sudo adduser www-data dialout
sudo adduser www-data video
sudo adduser www-data audio
sudo adduser www-data adm
sudo mkdir -p /var/www/public
sudo mkdir -p /var/www/static
sudo mkdir -p /var/www/Pictures/PiRobot
sudo mkdir -p /var/www/Videos/PiRobot
sudo chown -R www-data:www-data /var/www/
sudo cp -rf ../react/pirobot/public/* /var/www/public
sudo cp -rf ../react/pirobot/build/static/* /var/www/static
sudo cp -rf ../react/pirobot/build/index.html /var/www/

sudo cp pirobot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pirobot

# --- PulseAudio setup ---
echo "Installing PulseAudio..."
sudo apt-get install -y pulseaudio pulseaudio-utils libasound2-plugins

echo "Deploying PulseAudio config..."
sudo cp config/audio/pulse-system.pa /etc/pulse/system.pa || { echo "ERROR: failed to copy pulse-system.pa"; exit 1; }
sudo cp config/audio/asound.conf /etc/asound.conf || { echo "ERROR: failed to copy asound.conf"; exit 1; }
sudo cp config/audio/pulseaudio.service /etc/systemd/system/pulseaudio.service || { echo "ERROR: failed to copy pulseaudio.service"; exit 1; }

echo "Configuring PulseAudio permissions..."
sudo adduser www-data pulse-access

echo "Starting PulseAudio system service..."
sudo systemctl daemon-reload
sudo systemctl enable pulseaudio.service
sudo systemctl restart pulseaudio.service

echo "Verifying PulseAudio..."
for _ in $(seq 1 10); do
    sudo -u www-data pactl info > /dev/null 2>&1 && break
    sleep 1
done
if sudo -u www-data pactl info > /dev/null 2>&1; then
    echo "  PulseAudio: OK"
else
    echo "  WARNING: PulseAudio daemon not reachable — check: journalctl -u pulseaudio"
fi
if sudo -u www-data pactl list modules short 2>/dev/null | grep -q module-echo-cancel; then
    echo "  Echo cancellation (webrtc): OK"
else
    echo "  WARNING: module-echo-cancel not loaded — check /etc/pulse/system.pa"
    echo "  If webrtc AEC is unavailable on this build:"
    echo "  edit server/config/audio/pulse-system.pa (change aec_method=webrtc to aec_method=speex)"
    echo "  then re-run install.sh"
fi
# --- end PulseAudio setup ---

sudo systemctl restart pirobot