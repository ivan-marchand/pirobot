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
            sdp = msg.get("sdp")
            if not sdp:
                logger.warning("webrtc offer missing sdp field")
                return
            talking = bool(msg.get("talking", False))
            listening = bool(msg.get("listening", False))
            await self._webrtc.handle_offer(sdp, talking=talking, listening=listening)
        elif action == "ice_candidate":
            candidate = msg.get("candidate")
            sdp_mid = msg.get("sdpMid")
            sdp_mline_index = msg.get("sdpMLineIndex")
            if candidate is None or sdp_mid is None or sdp_mline_index is None:
                logger.warning("webrtc ice_candidate missing required fields")
                return
            await self._webrtc.handle_ice_candidate(
                candidate=candidate,
                sdp_mid=sdp_mid,
                sdp_mline_index=sdp_mline_index,
            )
        else:
            logger.warning(f"Unknown webrtc action {action!r}")

    def close(self):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._webrtc.close())
        except RuntimeError:
            # No running loop (e.g. called after event loop shut down); skip async cleanup
            pass
