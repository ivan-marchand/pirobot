from handlers.base import BaseHandler, register_handler
from light import Light


@register_handler(name="light", needs=["light"])
class LightHandler(BaseHandler):

    def __init__(self):
        super().__init__()
        self.register_for_message("light")

    async def process(self, message, protocol):
        if message["action"] in ["toggle", "toggle_front_light"]:
            Light.toggle_front_light()
            await self.server.send_status(protocol)
        elif message["action"] == "blink":
            Light.blink(**message["args"])
        elif message["action"] == "toggle_arm_light":
            Light.toggle_arm_light()
            await self.server.send_status(protocol)
        elif message["action"] == "set":
            Light.blink(**message["args"])
            await self.server.send_status(protocol)
