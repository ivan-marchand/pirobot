import logging
import os
from PIL import Image

from handlers.base import BaseHandler, register_handler

logger = logging.getLogger(__name__)


@register_handler(name="lcd", needs=["screen"])
class LcdHandler(BaseHandler):

    def __init__(self):
        super().__init__()
        self.register_for_message("lcd")
        self.pics_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../assets/Pics'))
        if not os.path.isdir(self.pics_path):
            self.pics_path = "/etc/pirobot/assets/Pics"

    async def process(self, message, protocol):
        if message["action"] == "display_picture":
            self.set_lcd_picture(message["args"]["name"])

    def set_lcd_picture(self, name):
        file_path = os.path.join(self.pics_path, f"{name}.png")
        if os.path.isfile(file_path):
            image = Image.open(file_path)
            image = image.resize((self.server.lcd.height, self.server.lcd.width)).convert('RGB')
            self.server.lcd.ShowImage(image)
        else:
            logger.info(f"Picture not found {name}")

    def display_frame(self, frame):
        from PIL import Image as PILImage
        img = PILImage.fromarray(frame, 'RGB')
        img = img.resize((self.server.lcd.height, self.server.lcd.width))
        self.server.lcd.ShowImage(img)

    def stop_video(self):
        from PIL import Image as PILImage
        img = PILImage.new('RGB', (self.server.lcd.height, self.server.lcd.width), color=(0, 0, 0))
        self.server.lcd.ShowImage(img)

