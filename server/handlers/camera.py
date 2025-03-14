import cv2
import datetime
import logging
import os
import time

from PIL import Image

from camera import Camera
from handlers.base import BaseHandler, register_handler
from models import Config

logger = logging.getLogger(__name__)

@register_handler("camera")
class CameraHandler(BaseHandler):

    def __init__(self):
        super().__init__()
        self.frame_rate = Camera.frame_rate
        self.video_start_ts = None
        self.frame_counter = 0
        self.video_source = "streaming"
        self.picture_source = "streaming"
        self.picture_destination = "file"
        self.picture_format = "png"
        self.capture_video = False
        self.capture_picture = False
        self.register_for_message("camera")
        self.register_for_event("camera", "new_streaming_frame")
        self.register_for_event("camera", "new_front_camera_frame")
        self.video_writer = None
        self.video_dir = os.path.join(os.environ["HOME"], "Videos/PiRobot")
        self.video_filename = None
        if not os.path.isdir(self.video_dir):
            os.makedirs(self.video_dir)
        self.picture_dir = os.path.join(os.environ["HOME"], "Pictures/PiRobot")
        if not os.path.isdir(self.picture_dir):
            os.makedirs(self.picture_dir)

    async def process(self, message, protocol):
        if message["action"] == "set_position":
            Camera.set_position(message["args"]["position"])
            await self.server.send_status(protocol)
        elif message["action"] == "center_position":
            Camera.center_position()
            await self.server.send_status(protocol)
        elif message["action"] == "start_video":
            if self.video_writer is not None:
                self.video_writer.release()
                self.video_writer = None
            self.video_source = message["args"].get("source", "streaming")
            self.capture_video = True
        elif message["action"] == "stop_video":
            self.capture_video = False
            self.video_start_ts = None
            self.frame_counter = 0
            if self.video_writer is not None:
                self.video_writer.release()
                self.video_writer = None
                self.video_filename = None
                await protocol.send_message("video", dict(status="new_file", filename=self.video_filename))
        elif message["action"] == "capture_picture":
            self.capture_picture = True
            self.picture_source = message["args"].get("source", "streaming")
            self.picture_format = message["args"].get("format", "png")
            self.picture_destination = message["args"].get("destination", "file")
        elif message["action"] == "toggle_overlay":
            Camera.overlay = not Camera.overlay
        elif message["action"] == "toggle_camera":
            if Camera.selected_camera == "front":
                Camera.selected_camera = "back"
            else:
                Camera.selected_camera = "front"
        elif message["action"] == "select_camera":
            selected_camera = message["args"].get("camera")
            if selected_camera in ["front", "back"]:
                Camera.selected_camera = selected_camera
            else:
                logger.warning(f"Invalid camera: {selected_camera}")
        else:
            logger.warning(f"Unknown message action {message.get('action')}")

    def get_filename(self):
        robot_name = Config.get("robot_name")
        creation_time = datetime.datetime.now().strftime("%y%m%d_%H%M%S")
        return f"{robot_name}_{self.video_source}_{creation_time}"

    def start_video(self, frame):
        self.video_filename = f"{self.get_filename()}.{Config.get('video_format')}"
        self.frame_rate = Camera.frame_rate
        self.video_writer = cv2.VideoWriter(
            filename=os.path.join(self.video_dir, self.video_filename),
            fourcc=cv2.VideoWriter_fourcc(*Config.get("video_codec")),
            fps=self.frame_rate,
            frameSize=(frame.shape[1], frame.shape[0]),
            isColor=True,
        )

    def receive_event(self, topic, event_type, data):
        if topic == "camera":
            video_source = None
            if event_type == "new_streaming_frame":
                video_source = "streaming"
            elif event_type == "new_front_camera_frame":
                video_source = "front"

            if video_source is not None:
                # Capturing Video?
                if self.capture_video and self.video_source == video_source:
                    self.record_video_frame(data["frame"])

                # Capturing Picture?
                if self.capture_picture and self.picture_source == video_source:
                    if self.picture_destination == "lcd":
                        if self.server.robot_has_screen:
                            frame = cv2.cvtColor(data["frame"], cv2.COLOR_BGR2RGB)
                            image = Image.fromarray(frame)
                            image = image.resize((self.server.lcd.height, self.server.lcd.width))
                            self.server.lcd.ShowImage(image)
                    else:
                        filename = self.get_filename()
                        cv2.imwrite(
                            os.path.join(self.picture_dir, f"{filename}.{self.picture_format}"), data["frame"]
                        )
                    self.capture_picture = False

                # Add REC indicator
                if video_source == "streaming":
                    if self.capture_video:
                        self.add_rec_indicator(data["frame"])
                    # Mode
                    if BaseHandler.state is not None:
                        self.add_mode_indicator(data["frame"])

    def add_rec_indicator(self, frame):
        # Add REC indicator
        res_x = len(frame[0])
        text = "REC"
        thickness = 2
        color = (0, 255, 0)
        font = cv2.FONT_HERSHEY_SIMPLEX
        fontScale = 0.8
        text_w, text_h = cv2.getTextSize(
            text=text, fontFace=font, fontScale=fontScale, thickness=thickness
        )[0]
        cv2.putText(
            frame, text, (int(res_x / 2 - text_w / 2), 5 + text_h), font, fontScale, color, thickness
        )

    def add_mode_indicator(self, frame):
        # Add REC indicator
        res_x = len(frame[0])
        thickness = 2
        color = (0, 255, 0)
        font = cv2.FONT_HERSHEY_SIMPLEX
        fontScale = 0.8

        state = BaseHandler.state.upper().replace("_", " ")
        text_w, text_h = cv2.getTextSize(text=state, fontFace=font, fontScale=fontScale, thickness=thickness)[0]
        cv2.putText(frame, state, (res_x - text_w - 5, 5 + text_h), font, fontScale, color, thickness)

    def record_video_frame(self, frame):
        if self.video_writer is None:
            self.start_video(frame)
        self.video_writer.write(frame)
        self.frame_counter += 1
        if self.video_start_ts is None:
            self.video_start_ts = time.time()
        else:
            expect_nb_of_frames = int((time.time() - self.video_start_ts) * self.frame_rate)
            nb_of_missing_frames = expect_nb_of_frames - self.frame_counter
            if nb_of_missing_frames > 1:
                for i in range(nb_of_missing_frames):
                    self.video_writer.write(frame)
                    self.frame_counter += 1
