APP_NAME=pirobot
DAEMON_NAME=pirobotd

# Resolve uv path (not always in PATH when run via SSH)
UV=$(which uv 2>/dev/null || echo "$HOME/.local/bin/uv")

# Ensure venv has access to system packages (needed for picamera2, RPi.GPIO etc.)
$UV venv --system-site-packages
$UV sync

$UV run pyinstaller manage.py $(ls handlers/* | grep -v __init__.py | grep -v base.py | grep -v __pycache__ | grep -v .pyc | sed -e 's/handlers\/\(\w\+\).py/ --hidden-import  handlers.\1/g') --collect-all cv2 --hidden-import picamera2 --hidden-import libcamera -F -n $DAEMON_NAME

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
sudo systemctl restart pirobot