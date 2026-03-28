from handlers.base import BaseHandler, register_handler
from models import Config


@register_handler("configuration")
class ConfigurationHandler(BaseHandler):

    def __init__(self):
        super().__init__()
        self.register_for_message("configuration")

    async def process(self, message, protocol):
        success, need_setup = await Config.process(message, protocol)
        if success:
            if need_setup:
                self.server.setup()
            # Update status
            await self.server.send_status(protocol)
