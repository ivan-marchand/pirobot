from handlers.base import BaseHandler, register_handler
from arm import Arm


@register_handler("arm")
class DriveHandler(BaseHandler):

    def __init__(self):
        super().__init__()
        self.register_for_message("arm")

    async def process(self, message, protocol):
        if message["action"] == "move":
            Arm.move(**message["args"])
            await self.server.send_status(protocol)
        elif message["action"] == "move_servo_to_position":
            Arm.move_servo_to_position(**message["args"])
            await self.server.send_status(protocol)
        elif message["action"] == "move_to_position":
            Arm.move_to_position(**message["args"])
            await self.server.send_status(protocol)
