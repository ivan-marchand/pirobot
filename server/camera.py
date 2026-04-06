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
    try:
        import picamera
        from picamera.array import PiRGBArray
    except ImportError:
        picamera = None
elif platform.machine() == "aarch64":  # Raspberry 64 bits
    try:
        import picamera2
    except ImportError:
        picamera2 = None

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


def _open_usb_capture(index):
    if platform.system() == "Linux":
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    else:
        cap = cv2.VideoCapture(index)
    return cap


def get_camera_index():
    for index in [0, 1]:
        cap = _open_usb_capture(index)
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
            self.device = _open_usb_capture(Camera.available_device)
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
        h, w = frame.shape[:2]
        resized = cv2.resize(overlay_frame,
                             [max(1, int((size[0] * w) / 100)), max(1, int((size[1] * h) / 100))],
                             interpolation=cv2.INTER_AREA)
        x_offset = int((pos[0] * w) / 100)
        y_offset = int((pos[1] * h) / 100)
        x_end = min(w, x_offset + resized.shape[1])
        y_end = min(h, y_offset + resized.shape[0])
        frame[y_offset:y_end, x_offset:x_end] = resized[:y_end - y_offset, :x_end - x_offset]

    def add_radar(self, frame, pos, size):
        h, w = frame.shape[:2]
        motor_status = Motor.serialize()
        left_us_distance, front_us_distance, right_us_distance = motor_status.get('us_distances')
        radius = 0.15 * w

        color = (0, 255, 0)
        thickness = 2

        def add_circle(distance, angle):
            normalized_distance = radius * distance / 0.5
            if normalized_distance <= radius:
                cx = normalized_distance * math.sin(angle * math.pi / 180)
                cy = normalized_distance * math.cos(angle * math.pi / 180)
                x = int(cx + w // 2)
                y = int(h - cy)
                cv2.circle(frame, (x, y), radius=4, color=(0, 0, 255), thickness=2)

        cv2.circle(frame, (w // 2, h), radius=int(radius), color=(0, 255, 0), thickness=2)
        cv2.line(frame,
                 (w // 2, h),
                 (int(w // 2 - radius * math.sin(math.pi / 4)), int(h - radius * math.sin(math.pi / 4))),
                 color,
                 thickness)
        cv2.circle(frame, (w // 2, h), radius=int(2 * radius / 3), color=(0, 255, 0), thickness=2)
        cv2.line(frame,
                 (w // 2, h),
                 (w // 2, int(h - radius)),
                 color,
                 thickness)
        cv2.circle(frame, (w // 2, h), radius=int(radius / 3), color=(0, 255, 0), thickness=2)
        cv2.line(frame,
                 (w // 2, h),
                 (int(w // 2 + radius * math.sin(math.pi / 4)), int(h - radius * math.sin(math.pi / 4))),
                 color,
                 thickness)

        if left_us_distance is not None:
            add_circle(left_us_distance, -45)
        if front_us_distance is not None:
            add_circle(front_us_distance, 0)
        if right_us_distance is not None:
            add_circle(right_us_distance, 45)

    def add_navigation_lines(self, frame):
        h, w = frame.shape[:2]
        color = (0, 255, 0)
        thickness = 2

        # Visor
        radius = 30
        y_offest = 30
        center_x = w // 2
        center_y = h // 2 + y_offest
        cv2.line(frame, (center_x, center_y + (radius + 10)), (center_x, center_y - (radius + 10)), color, thickness)
        cv2.line(frame, (center_x + (radius + 10), center_y), (center_x - (radius + 10), center_y), color, thickness)
        cv2.circle(frame, (center_x, center_y), radius, color, thickness)

        # Path
        path_bottom = 100
        cv2.line(frame, (center_x, center_y), (path_bottom, h), color, thickness)
        cv2.line(frame, (center_x, center_y), (w - path_bottom, h), color, thickness)

        # Speed and distance
        font = cv2.FONT_HERSHEY_SIMPLEX
        fontScale = 0.8
        color = (0, 255, 0)

        motor_status = Motor.serialize()

        # ODO
        _, text_h = cv2.getTextSize(text="ODO", fontFace=font, fontScale=fontScale, thickness=thickness)[0]
        cv2.putText(frame, f"ODO: {motor_status['abs_distance'] / 1000:.2f} m", (5, 5 + text_h), font, fontScale, color, thickness)

        # Left
        cv2.putText(frame, f"{motor_status['left']['speed_rpm']} RPM", (5, h - 15), font, fontScale, color, thickness)
        cv2.rectangle(frame, (5, h - 50), (5 + 40, h - 50 - 400), color, thickness)
        cv2.rectangle(frame, (5, h - 50 - 200), (5 + 40, h - 50 - 200 - int(motor_status['left']['duty'] * 2)), color, -1)

        # Right
        right_speed_str = f"{motor_status['right']['speed_rpm']} RPM"
        text_w, text_h = cv2.getTextSize(text=right_speed_str, fontFace=font, fontScale=fontScale, thickness=thickness)[0]
        cv2.putText(frame, right_speed_str, (w - text_w - 5, h - 15), font, fontScale, color, thickness)
        cv2.rectangle(frame, (w - 5, h - 50), (w - 5 - 40, h - 50 - 400), color, thickness)
        cv2.rectangle(frame, (w - 5, h - 50 - 200), (w - 5 - 40, h - 50 - 200 - int(motor_status['right']['duty'] * 2)), color, -1)

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
    _streaming_clients = 0
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
            if not Camera.capturing:
                Camera.available_device = get_camera_index()
            Camera.status = "KO" if Camera.available_device is None else "OK"
        else:
            Camera.status = "OK"
        if Camera.capturing:
            if Camera.capturing_task is not None:
                Camera.capturing_task.cancel()
                Camera.capturing_task = None
            Camera.capturing = False
            Camera.start_continuous_capture()

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

        frame_delay = 1.0 / Camera.frame_rate
        my_front_device = None
        my_back_device = None
        try:
            my_front_device = CaptureDevice(
                resolution=front_resolution,
                capturing_device=front_capturing_device,
                angle=front_angle
            )
            Camera.front_capture_device = my_front_device
            if Config.get("robot_has_back_camera") and back_capturing_device != "none":
                if platform.machine() in ["aarch", "aarch64"]:
                    my_back_device = CaptureDevice(
                        resolution=back_resolution,
                        capturing_device=back_capturing_device,
                        angle=back_angle
                    )
                else:
                    my_back_device = my_front_device
                Camera.back_capture_device = my_back_device
            else:
                Camera.back_capture_device = None
            loop = asyncio.get_running_loop()
            while Camera.capturing:
                t0 = loop.time()
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
                            for callback in list(Camera.new_streaming_frame_callbacks.values()):
                                try:
                                    callback(frame)
                                except Exception:
                                    logger.error("Exception in streaming frame callback", exc_info=True)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.error("Unexpected exception in continuous capture", exc_info=True)
                elapsed = loop.time() - t0
                await asyncio.sleep(max(0.0, frame_delay - elapsed))
        finally:
            if my_front_device is not None:
                if Camera.front_capture_device is my_front_device:
                    Camera.front_capture_device = None
                await asyncio.to_thread(my_front_device.close)
            if my_back_device is not None and my_back_device is not my_front_device:
                if Camera.back_capture_device is my_back_device:
                    Camera.back_capture_device = None
                await asyncio.to_thread(my_back_device.close)
            if Camera.capturing_task is None or Camera.capturing_task is asyncio.current_task():
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
        Camera._streaming_clients += 1
        Camera.streaming = True
        Camera.start_continuous_capture()

    @staticmethod
    def stop_streaming():
        Camera._streaming_clients = max(0, Camera._streaming_clients - 1)
        if Camera._streaming_clients == 0:
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
