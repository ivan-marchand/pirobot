import cv2

from handlers.base import BaseHandler, register_handler
from models import Config
from uart import UART, MessageOriginator, MessageType


@register_handler("battery", needs=["battery_tester"])
class BatteryHandler(BaseHandler):

    def __init__(self):
        super().__init__()
        self.battery_level = None
        self.min_battery_volt = 11.5
        self.max_battery_volt = 13.0
        self.register_for_event("camera", "new_front_camera_frame")
        UART.register_consumer("battery_handler", self, MessageOriginator.battery, MessageType.status)

    def setup(self, server):
        super().setup(server)
        r1 = Config.get("battery_tester_r1")
        r2 = Config.get("battery_tester_r2")
        self.min_battery_volt = Config.get("battery_min_volt")
        self.max_battery_volt = Config.get("battery_max_volt")
        # Configure tester and et up to date battery level
        UART.write(f"B:C:{r1}:{r2}")
        UART.write("B:S")

    def add_battery_level(self, frame):
        # Add REC indicator
        text = f"BAT: {self.battery_level}%"
        thickness = 2
        if self.battery_level < 10:
            color = (0, 0, 255)
        else:
            color = (0, 255, 0)
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.8
        text_w, text_h = cv2.getTextSize(
            text=text, fontFace=font, fontScale=font_scale, thickness=thickness
        )[0]
        cv2.putText(
            frame, text, (5, 2 * (10 + text_h)), font, font_scale, color, thickness
        )

    def receive_uart_message(self, message, originator, message_type):
        battery_volt = float(message[0])
        self.battery_level = int(
            100 * (battery_volt - self.min_battery_volt) / (self.max_battery_volt - self.min_battery_volt)
        )
        self.battery_level = min(100, max(0, self.battery_level))

    def receive_event(self, topic, event_type, data):
        if self.battery_level is None:
            self.battery_level = 0
        if topic == "camera" and event_type == "new_front_camera_frame" and len(data["frame"]) > 0 and not data.get("overlay", False):
            self.add_battery_level(data["frame"])
