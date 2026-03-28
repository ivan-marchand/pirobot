# PiRobot
https://pirobot.net/

# Install
```
sudo apt update
sudo apt install git
mkdir git
cd git
https://github.com/ivan-marchand/pirobot.git
cd pirobot/server

sudo apt install python3-pip
pip install uv

uv sync

./install.sh

sudo systemctl enable pirobot
sudo apt install espeak
```