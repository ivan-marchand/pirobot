from handlers.base import BaseHandler, register_handler
from game import Games
from models import Config
from sfx import SFX


@register_handler("talk")
class TalkHandler(BaseHandler):

    def __init__(self):
        super().__init__()
        self.register_for_message("talk")

    async def process(self, message, protocol):
        if message["action"] == "play":
            self.play_message(message["args"].get("destination", "lcd"), message["args"]["message"])

    def play_message(self, destination, message):
        if message.startswith("!"):
            cmd = message[1:].split(' ')
            if len(cmd) > 1:
                command = cmd[0]
                args = cmd[1:]
                if command == "img" and args and self.server.robot_has_screen:
                    lcd_handler = BaseHandler.get_handler("lcd")
                    if lcd_handler is not None:
                        lcd_handler.set_lcd_picture(args[0])
                    message = None
                elif command == "sfx" and args and self.server.robot_has_speaker:
                    message = SFX.play(args[0])
                elif command == "play":
                    message = Games.play(args[0], args[1:])
                else:
                    message = None
            else:
                message = None
        if message is not None:
            if destination == "lcd" and self.server.robot_has_screen:
                self.server.terminal.text(message)
            elif destination == "audio" and self.server.robot_has_speaker:
                if self.server.voice_engine._inLoop:
                    self.server.voice_engine.endLoop()

                self.server.voice_engine.setProperty('voice', Config.get("voice_id"))
                self.server.voice_engine.setProperty('rate', Config.get("voice_rate"))
                self.server.voice_engine.setProperty('volume', Config.get("voice_volume"))
                self.server.voice_engine.say(message)
                self.server.voice_engine.runAndWait()

