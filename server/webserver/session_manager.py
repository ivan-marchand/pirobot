from abc import ABC, abstractmethod
import asyncio
import json
import logging

from server import Server
from webrtc import WebRTCSessionManager

logger = logging.getLogger(__name__)


class SessionManager(ABC):

    def __init__(self, sid):
        self.sid = sid

    def __del__(self):
        self.close()

    def close(self):
        pass

    @abstractmethod
    async def process_message(self, message):
        pass


class RobotSessionManager(SessionManager):

    def __init__(self, sid, protocol):
        super().__init__(sid)
        self.protocol = protocol
        self._webrtc = WebRTCSessionManager(send_message=protocol.send_message_raw)

    async def process_message(self, message):
        message_dict = json.loads(message)
        topic = message_dict.get("topic")
        if topic == "robot":
            await Server.process(message_dict.get("message"), self.protocol)
        elif topic == "webrtc":
            await self._dispatch_webrtc(message_dict)
        else:
            logger.warning(f"Unknown topic {topic}")

    async def _dispatch_webrtc(self, msg: dict) -> None:
        action = msg.get("action")
        if action == "offer":
            await self._webrtc.handle_offer(msg["sdp"])
        elif action == "ice_candidate":
            await self._webrtc.handle_ice_candidate(
                candidate=msg["candidate"],
                sdp_mid=msg["sdpMid"],
                sdp_mline_index=msg["sdpMLineIndex"],
            )
        else:
            logger.warning(f"Unknown webrtc action {action!r}")

    def close(self):
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(self._webrtc.close())
        else:
            loop.run_until_complete(self._webrtc.close())
