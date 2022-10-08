import io
import math
import platform
import sys
import threading
import time
import traceback

import cv2
import numpy as np
from motor.motor import Motor

from restapi.models import Config
if platform.machine() == "aarch":  # Mac OS
    import picamera
    from picamera.array import PiRGBArray
elif platform.machine() == "aarch64":
    import picamera2

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

target = None
camera_semaphore = threading.Semaphore()

def getCameraIndex():
    # checks the first 10 indexes.
    for index in [1, 0]:
        cap = cv2.VideoCapture(index)
        if cap.read()[0]:
            cap.release()
            return index
    return None

class CaptureDevice(object):
    target = None
    target_img = None
    catpures = []
    available_device = None

    def __init__(self, resolution, capturing_device):
        self.capturing_device = capturing_device
        self.frame_counter = 0
        self.res_x, self.res_y = resolution.split('x')
        self.res_x, self.res_y = int(self.res_x), int(self.res_y)
        if self.capturing_device == "usb":  # USB Camera?
            self.device = cv2.VideoCapture(Camera.available_device)
            self.device.set(cv2.CAP_PROP_BUFFERSIZE, 2)
            self.device.set(3, self.res_x)
            self.device.set(4, self.res_y)
        else:
            if platform.machine() == "aarch64":
                self.device = picamera2.Picamera2()
                config = self.device.create_preview_configuration({"size": (self.res_x, self.res_y), "format": "RGB888"})
                print(config)
                self.device.configure(config)
                self.device.start()
            else:
                self.device = picamera.PiCamera(resolution=resolution)

    def _add_target(self, frame):
        rect_size = 70
        center = [int((CaptureDevice.target[0] * self.res_x) / 100), int((CaptureDevice.target[1] * self.res_y) / 100)]
        if CaptureDevice.target_img is not None and self.frame_counter % 10 == 0:

            result = cv2.matchTemplate(frame, CaptureDevice.target_img, cv2.TM_CCORR_NORMED)
            # We want the minimum squared difference
            mn, mx, mnLoc, mxLoc = cv2.minMaxLoc(result)

            # Draw the rectangle:
            # Extract the coordinates of our best match
            if mx > 0.95:
                center = [mxLoc[0] + rect_size, mxLoc[1] + rect_size]
                CaptureDevice.target_img = frame[center[1] - rect_size:center[1] + rect_size, center[0] - rect_size:center[0] + rect_size]
        else:
            CaptureDevice.target_img = frame[center[1] - rect_size:center[1] + rect_size, center[0] - rect_size:center[0] + rect_size]



        CaptureDevice.target = [100 * center[0] / self.res_x, 100 * center[1] / self.res_y]


        cv2.rectangle(frame, [center[0] - 10, center[1] - 10], [center[0] + 10, center[1] + 10], (0, 0, 255), 2)

    def add_overlay(self, frame, overlay_frame, pos, size):
        resized = cv2.resize(overlay_frame,
                             [int((size[0] * self.res_x) / 100), int((size[1] * self.res_y) / 100)],
                             interpolation=cv2.INTER_AREA)
        x_offset, y_offset = [int((pos[0] * self.res_x) / 100), int((pos[1] * self.res_y) / 100)]

        frame[y_offset:y_offset + resized.shape[0], x_offset:x_offset + resized.shape[1]] = resized

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
        fontScale = 1
        color = (0, 255, 0)
        thickness = 2

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
        if self.capturing_device == "usb":
            ret, frame = self.device.retrieve()
            return cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
        else:  # picamera
            if platform.machine() == "aarch64":
                frame = self.device.capture_array()
                return cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
            else:
                output = PiRGBArray(self.device)
                self.device.capture(output, format="bgr", use_video_port=True)
                return cv2.cvtColor(output.array, cv2.COLOR_BGR2BGRA)
 
    def capture(self):
        max_retries = 3
        while max_retries > 0:
            max_retries -= 1
            try:
                if self.capturing_device == "usb":
                    camera_semaphore.acquire()
                    ret, frame = self.device.read()
                    camera_semaphore.release()
                    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
                else:  # picamera
                    output = PiRGBArray(self.device)
                    self.device.capture(output, format="rgb")
                    return cv2.cvtColor(output.array, cv2.COLOR_BGRA2BGR)
            except:
                print ("Failed to capture image, retrying")
                traceback.print_exc()
                time.sleep(0.1)

    def capture_continuous(self, stream, format='jpeg'):
        if self.capturing_device == "usb":
            while True:
                camera_semaphore.acquire()
                ret, frame = self.device.read()
                camera_semaphore.release()
                self.frame_counter += 1

                #if CaptureDevice.target is not None:
                #    self._add_target(frame)

                # self.add_navigation_lines(frame)

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)

                yield cv2.imencode('.jpg', rgb)[1].tostring()
        else:
            for frame in self.device.capture_continuous(stream,
                                                        format=format,
                                                        use_video_port=True):
                self.frame_counter += 1
                yield frame.getvalue()

    def close(self):
        if self.capturing_device == "usb":
            self.device.release()
        else:
            self.device.close()


class Camera(object):
    status = "UK"
    streaming = False
    overlay = True
    selected_camera = "front"
    front_capture_device = None
    arm_capture_device = None

    @staticmethod
    def setup():
        Camera.available_device = getCameraIndex()
        if Camera.available_device is None:
            Camera.status = "KO"
        else:
            Camera.status = "OK"

    @staticmethod
    def stream():
        config = Config.get_config()
        if platform.machine() not in ["aarch", "aarch64"]:
            front_capturing_device = "usb"
            front_resolution = '1280x720'
        else:
            front_capturing_device = config.get('front_capturing_device', 'usb')
            front_resolution = config.get('front_capturing_resolution', '1280x720')
            arm_capturing_device = config.get('arm_capturing_device', 'picamera')
            arm_resolution = config.get('back_capturing_resolution', '640x480')
        Camera.front_capture_device = CaptureDevice(resolution=front_resolution,
                                                    capturing_device=front_capturing_device)
        if platform.machine() != "aarch":
            Camera.arm_capture_device = Camera.front_capture_device
        else:
            Camera.arm_capture_device = CaptureDevice(resolution=arm_resolution,
                                                       capturing_device=arm_capturing_device)

        framerate = float(config.get('capturing_framerate', 5))
        stream = io.BytesIO()
        try:
            Camera.streaming = True
            frame_delay = 1.0 / framerate
            last_frame_ts = 0
            while Camera.streaming:
                Camera.front_capture_device.grab()
                Camera.arm_capture_device.grab()

                if time.time() > last_frame_ts + frame_delay:
                    last_frame_ts = time.time()
                    if Camera.selected_camera == "front":
                        frame = Camera.front_capture_device.retrieve()
                        # Navigation
                        Camera.front_capture_device.add_navigation_lines(frame)
                    else:
                        frame = Camera.arm_capture_device.retrieve()

                    if Camera.overlay:
                        if Camera.selected_camera == "front":
                            overlay_frame = Camera.arm_capture_device.retrieve()
                            Camera.front_capture_device.add_overlay(frame, overlay_frame, [75, 0], [25, 25])
                        else:
                            overlay_frame = Camera.front_capture_device.retrieve()
                            Camera.arm_capture_device.add_overlay(frame, overlay_frame, [75, 0], [25, 25])


                    frame = cv2.imencode('.jpg', frame)[1].tostring()
                    stream.truncate()
                    stream.seek(0)
                    yield "--FRAME\r\n"
                    yield "Content-Type: image/jpeg\r\n"
                    yield "Content-Length: %i\r\n" % len(frame)
                    yield "\r\n"
                    yield frame
                    yield "\r\n"
        except Exception as e:
            traceback.print_exc()
        finally:
            Camera.front_capture_device.close()
            Camera.front_capture_device = None
            Camera.arm_capture_device.close()
            Camera.arm_capture_device = None
            Camera.streaming = False

    @staticmethod
    def stream_setup(selected_camera, overlay):
        Camera.selected_camera = selected_camera
        Camera.overlay = overlay

    @staticmethod
    def select_target(x, y):
        CaptureDevice.target = [x, y]

    @staticmethod
    def get_target_position(x, y):
        # Distance on y axis
        a = 0
        for n, p in enumerate(reversed(poly_coefficients)):
            a += p * math.pow(min(max_y_pos, (100 - y)), n)
        y_pos = H * math.tan(a)

        x_pos = (MAX_DISTANCE / (MAX_DISTANCE - min(y_pos, MAX_DISTANCE - 0.1))) * ((x - 50) / 50) * ROBOT_WIDTH/2
        lense_coeff_x_pos = Config.get('lense_coeff_x_pos')
        return x_pos * lense_coeff_x_pos, y_pos

    @staticmethod
    def capture_image(camera):
        if camera == "front" and Camera.front_capture_device is not None:
            return Camera.front_capture_device.capture()
        elif camera == "arm" and Camera.arm_capture_device is not None:
            return Camera.arm_capture_device.capture()


    @staticmethod
    def serialize():
        return {
            'status': Camera.status,
            'streaming': Camera.streaming,
            'overlay': Camera.overlay,
            'selected_camera': Camera.selected_camera
        }
