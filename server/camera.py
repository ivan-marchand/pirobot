import asyncio
import cv2
import logging
import numpy as np
import math
import platform


from handlers.base import BaseHandler
from models import Config
from motor.motor import Motor
from servo.servo_handler import ServoHandler

if platform.machine() == "aarch":  # Raspberry 32 bits
    import picamera
    from picamera.array import PiRGBArray
elif platform.machine() == "aarch64":  # Raspberry 64 bits
    import picamera2

logger = logging.getLogger(__name__)

# Calculate model to covert the position of a pixel to the physical position on the floor,
# using measurements (distances & y_pos) & polynomial regression
H = 70
MAX_DISTANCE = 1.8
ROBOT_WIDTH = 0.56  # in m

reference = dict(
    distances=[d / 100 for d in [15, 20, 30, 40, 50, 60, 68, 80, 90, 120, 150, 180]],
    y_pos=[100 - n for n in [100, 91.3, 79.2, 73.4, 69.9, 67.15, 65.6, 64.23, 62.86, 61.1, 59.9, 58.96]]
)
# Angle of the target
alpha = np.arctan([d / H for d in reference['distances']])
poly_coefficients = np.polyfit(reference['y_pos'], alpha, 3)
max_y_pos = 42


def get_camera_index():
    for index in [1, 0]:
        cap = cv2.VideoCapture(index)
        for _ in range(5):  # allow camera to warm up
            ret, _ = cap.read()
            if ret:
                cap.release()
                return index
        cap.release()
    return None


class CaptureDevice(object):

    def __init__(self, resolution, capturing_device, angle):
        self.capturing_device = capturing_device
        self.frame_counter = 0
        self.res_x, self.res_y = resolution.split('x')
        self.res_x, self.res_y = int(self.res_x), int(self.res_y)
        self.angle = angle
        if self.capturing_device == "usb":  # USB Camera?
            self.device = cv2.VideoCapture(Camera.available_device)
            self.device.set(cv2.CAP_PROP_FRAME_WIDTH, self.res_x)
            self.device.set(cv2.CAP_PROP_FRAME_HEIGHT, self.res_y)
        else:
            if platform.machine() == "aarch64":
                self.device = picamera2.Picamera2()
                config = self.device.create_preview_configuration({"size": (self.res_x, self.res_y), "format": "RGB888"})
                self.device.configure(config)
                self.device.start()
            else:
                self.device = picamera.PiCamera(resolution=resolution)

    def add_overlay(self, frame, overlay_frame, pos, size):
        resized = cv2.resize(overlay_frame,
                             [int((size[0] * self.res_x) / 100), int((size[1] * self.res_y) / 100)],
                             interpolation=cv2.INTER_AREA)
        x_offset, y_offset = [int((pos[0] * self.res_x) / 100), int((pos[1] * self.res_y) / 100)]

        frame[y_offset:y_offset + resized.shape[0], x_offset:x_offset + resized.shape[1]] = resized

    def add_radar(self, frame, pos, size):
        motor_status = Motor.serialize()
        left_us_distance, front_us_distance, right_us_distance = motor_status.get('us_distances')
        radius = 0.15 * self.res_x

        color = (0, 255, 0)
        thickness = 2

        def add_circle(distance, angle):
            normalized_distance = radius * distance / 0.5
            if normalized_distance <= radius:
                cx = normalized_distance * math.sin(angle * math.pi / 180)
                cy = normalized_distance * math.cos(angle * math.pi / 180)
                x = int(cx + self.res_x // 2)
                y = int(self.res_y - cy)
                cv2.circle(frame, (x, y), radius=4, color=(0, 0, 255), thickness=2)

        cv2.circle(frame, (self.res_x // 2, self.res_y), radius=int(radius), color=(0, 255, 0), thickness=2)
        cv2.line(frame,
                 (self.res_x // 2, self.res_y),
                 (int(self.res_x // 2 - radius * math.sin(math.pi / 4)), int(self.res_y - radius * math.sin(math.pi / 4))),
                 color,
                 thickness)
        cv2.circle(frame, (self.res_x // 2, self.res_y), radius=int(2 * radius / 3), color=(0, 255, 0), thickness=2)
        cv2.line(frame,
                 (self.res_x // 2, self.res_y),
                 (self.res_x // 2, int(self.res_y - radius)),
                 color,
                 thickness)
        cv2.circle(frame, (self.res_x // 2, self.res_y), radius=int(radius / 3), color=(0, 255, 0), thickness=2)
        cv2.line(frame,
                 (self.res_x // 2, self.res_y),
                 (int(self.res_x // 2 + radius * math.sin(math.pi / 4)), int(self.res_y - radius * math.sin(math.pi / 4))),
                 color,
                 thickness)

        if left_us_distance is not None:
            add_circle(left_us_distance, -45)
        if front_us_distance is not None:
            add_circle(front_us_distance, 0)
        if right_us_distance is not None:
            add_circle(right_us_distance, 45)

    def add_navigation_lines(self, frame):
        color = (0, 255, 0)
        thickness = 2

        # Visor
        radius = 30
        y_offest = 30
        center_x = self.res_x // 2
        center_y = self.res_y // 2 + y_offest
        cv2.line(frame, (center_x, center_y + (radius + 10)), (center_x, center_y - (radius + 10)), color, thickness)
        cv2.line(frame, (center_x + (radius + 10), center_y), (center_x - (radius + 10), center_y), color, thickness)
        cv2.circle(frame, (center_x, center_y), radius, color, thickness)

        # Path
        path_bottom = 100
        cv2.line(frame, (center_x, center_y), (path_bottom, self.res_y), color, thickness)
        cv2.line(frame, (center_x, center_y), (self.res_x - path_bottom, self.res_y), color, thickness)

        # Speed and distance
        font = cv2.FONT_HERSHEY_SIMPLEX
        fontScale = 0.8
        color = (0, 255, 0)

        motor_status = Motor.serialize()

        # ODO
        _, text_h = cv2.getTextSize(text="ODO", fontFace=font, fontScale=fontScale, thickness=thickness)[0]
        cv2.putText(frame, f"ODO: {motor_status['abs_distance'] / 1000:.2f} m", (5, 5 + text_h), font, fontScale, color, thickness)

        # Left
        cv2.putText(frame, f"{motor_status['left']['speed_rpm']} RPM", (5, self.res_y - 15), font, fontScale, color, thickness)
        cv2.rectangle(frame, (5, self.res_y - 50), (5 + 40, self.res_y - 50 - 400), color, thickness)
        cv2.rectangle(frame, (5, self.res_y - 50 - 200), (5 + 40, self.res_y - 50 - 200 - int(motor_status['left']['duty'] * 2)), color, -1)

        # Right
        right_speed_str = f"{motor_status['right']['speed_rpm']} RPM"
        text_w, text_h = cv2.getTextSize(text=right_speed_str, fontFace=font, fontScale=fontScale, thickness=thickness)[0]
        cv2.putText(frame, right_speed_str, (self.res_x - text_w - 5, self.res_y - 15), font, fontScale, color, thickness)
        cv2.rectangle(frame, (self.res_x - 5, self.res_y - 50), (self.res_x - 5 - 40, self.res_y - 50 - 400), color, thickness)
        cv2.rectangle(frame, (self.res_x - 5, self.res_y - 50 - 200), (self.res_x - 5 - 40, self.res_y - 50 - 200 - int(motor_status['right']['duty'] * 2)), color, -1)

    def grab(self):
        if self.capturing_device == "usb":
            self.device.grab()

    def retrieve(self):
        self.frame_counter += 1
        if self.capturing_device == "usb":
            ret, frame = self.device.retrieve()
            return frame
        else:  # picamera
            if platform.machine() == "aarch64":
                frame = self.device.capture_array()
                return frame
            else:
                output = PiRGBArray(self.device)
                self.device.capture(output, format="bgr", use_video_port=True)
                return frame

    def close(self):
        if self.capturing_device == "usb":
            self.device.release()
        else:
            self.device.close()


class Camera(object):
    status = "UK"
    streaming = False
    capturing = False
    capturing_task = None
    frame_rate = 5
    overlay = True
    selected_camera = "front"
    front_capture_device = None
    back_capture_device = None
    has_camera_servo = False
    servo_id = 1
    servo_center_position = 60
    servo_position = 0
    new_streaming_frame_callbacks = {}
    available_device = None


    @staticmethod
    def add_new_streaming_frame_callback(name, callback):
        Camera.new_streaming_frame_callbacks[name] = callback

    @staticmethod
    def remove_new_streaming_frame_callback(name):
        Camera.new_streaming_frame_callbacks.pop(name, None)

    @staticmethod
    def setup():
        Camera.has_camera_servo = Config.get("robot_has_camera_servo")
        Camera.servo_center_position = Config.get("camera_center_position")
        Camera.servo_id = Config.get("camera_servo_id")
        Camera.center_position()
        Camera.frame_rate = Config.get("capturing_framerate")
        if Config.get('front_capturing_device') == "usb" or Config.get('back_capturing_device') == "usb":
            Camera.available_device = get_camera_index()
            Camera.status = "KO" if Camera.available_device is None else "OK"
        else:
            Camera.status = "OK"

    @staticmethod
    def set_position(position):
        if Camera.has_camera_servo:
            Camera.servo_position = int(position)
            ServoHandler.move(Camera.servo_id, 100 - Camera.servo_position)

    @staticmethod
    def center_position():
        Camera.set_position(Camera.servo_center_position)

    @staticmethod
    async def capture_continuous():
        front_capturing_device = Config.get('front_capturing_device')
        front_resolution = Config.get('front_capturing_resolution')
        front_angle = Config.get('front_capturing_angle')
        back_capturing_device = Config.get('back_capturing_device')
        back_resolution = Config.get('back_capturing_resolution')
        back_angle = Config.get('back_capturing_angle')

        Camera.capturing = True
        frame_delay = 1.0 / Camera.frame_rate
        try:
            Camera.front_capture_device = CaptureDevice(
                resolution=front_resolution,
                capturing_device=front_capturing_device,
                angle=front_angle
            )
            if Config.get("robot_has_back_camera") and back_capturing_device not in [None, "none"]:
                if platform.machine() in ["aarch", "aarch64"]:
                    Camera.back_capture_device = CaptureDevice(
                        resolution=back_resolution,
                        capturing_device=back_capturing_device,
                        angle=back_angle
                    )
                else:
                    Camera.back_capture_device = Camera.front_capture_device
            else:
                Camera.back_capture_device = None
            while Camera.capturing:
                try:
                    await asyncio.to_thread(Camera.front_capture_device.grab)
                    if Camera.back_capture_device is not None:
                        await asyncio.to_thread(Camera.back_capture_device.grab)

                    frame_delay = 1.0 / Camera.frame_rate
                    if Camera.back_capture_device is None or Camera.selected_camera == "front":
                        frame = await asyncio.to_thread(Camera.front_capture_device.retrieve)
                        BaseHandler.emit_event(
                            topic="camera", event_type="new_front_camera_frame", data=dict(frame=frame),
                        )
                        Camera.front_capture_device.add_navigation_lines(frame)
                        Camera.front_capture_device.add_radar(frame, [50, 0], [25, 25])
                    else:
                        frame = await asyncio.to_thread(Camera.back_capture_device.retrieve)
                        BaseHandler.emit_event(
                            topic="camera", event_type="new_back_camera_frame", data=dict(frame=frame),
                        )

                    if Camera.back_capture_device is not None and Camera.overlay:
                        if Camera.selected_camera == "front":
                            overlay_frame = await asyncio.to_thread(Camera.back_capture_device.retrieve)
                            BaseHandler.emit_event(
                                topic="camera",
                                event_type="new_back_camera_frame",
                                data=dict(frame=overlay_frame, overlay=True),
                            )
                            Camera.front_capture_device.add_overlay(frame, overlay_frame, [75, 0], [25, 25])
                        else:
                            overlay_frame = await asyncio.to_thread(Camera.front_capture_device.retrieve)
                            BaseHandler.emit_event(
                                topic="camera",
                                event_type="new_front_camera_frame",
                                data=dict(frame=overlay_frame, overlay=True),
                            )
                            Camera.back_capture_device.add_overlay(frame, overlay_frame, [75, 0], [25, 25])

                    if frame is not None:
                        BaseHandler.emit_event(
                            topic="camera", event_type="new_streaming_frame", data=dict(frame=frame),
                        )

                        if Camera.streaming:
                            jpeg_bytes = cv2.imencode('.jpg', frame)[1].tobytes()
                            for callback in Camera.new_streaming_frame_callbacks.values():
                                try:
                                    callback(jpeg_bytes)
                                except Exception:
                                    logger.error("Exception in streaming frame callback", exc_info=True)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.error("Unexpected exception in continuous capture", exc_info=True)
                await asyncio.sleep(frame_delay)
        finally:
            if Camera.front_capture_device is not None:
                await asyncio.to_thread(Camera.front_capture_device.close)
                Camera.front_capture_device = None
            if Camera.back_capture_device is not None:
                await asyncio.to_thread(Camera.back_capture_device.close)
                Camera.back_capture_device = None
            Camera.capturing = False
            logger.info("Stop Capture")

    @staticmethod
    def start_continuous_capture():
        if not Camera.capturing or Camera.capturing_task is None or Camera.capturing_task.done():
            Camera.capturing = True
            logger.info("Start capture")
            Camera.capturing_task = asyncio.get_running_loop().create_task(Camera.capture_continuous())

    @staticmethod
    def start_streaming():
        Camera.start_continuous_capture()
        Camera.streaming = True

    @staticmethod
    def stop_streaming():
        Camera.streaming = False

    @staticmethod
    def stop_continuous_capture():
        if not Camera.streaming:
            Camera.capturing = False

    @staticmethod
    def stream_setup(selected_camera, overlay):
        Camera.selected_camera = selected_camera
        Camera.overlay = overlay

    @staticmethod
    def get_target_position(x, y):
        # Distance on y axis
        a = 0
        for n, p in enumerate(reversed(poly_coefficients)):
            a += p * math.pow(min(max_y_pos, (100 - y)), n)
        y_pos = H * math.tan(a)

        x_pos = (MAX_DISTANCE / (MAX_DISTANCE - min(y_pos, MAX_DISTANCE - 0.1))) * ((x - 50) / 50) * ROBOT_WIDTH/2
        return x_pos * Config.get("lense_coeff_x_pos"), y_pos

    @staticmethod
    def serialize():
        return {
            'status': Camera.status,
            'streaming': Camera.streaming,
            'overlay': Camera.overlay,
            'selected_camera': Camera.selected_camera,
            'position': Camera.servo_position,
            'center_position': Camera.servo_center_position
        }
