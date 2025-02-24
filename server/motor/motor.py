import logging
import math

from handlers.base import BaseHandler
from models import Config
from motor.motor_pico import PicoMotor

logger = logging.getLogger(__name__)

MOTOR_CONTROLLERS = dict(
    pico=PicoMotor
)


class Motor(object):
    status = "UK"
    _controller = None

    @staticmethod
    def setup():
        # Motor Initialization
        motor_controller = Config.get("motor_controller")
        Motor._controller = MOTOR_CONTROLLERS.get(motor_controller)
        if Motor._controller is not None:
            Motor._controller.setup()
        else:
            logger.error(f"Unknown motor controller: {motor_controller}")
        Motor.wheel_d = Config.get("wheel_d")
        Motor.robot_width = Config.get("robot_width")

    @staticmethod
    def get_status():
        return Motor._controller.status

    @staticmethod
    def stop():
        if BaseHandler.state == "patrolling":
            BaseHandler.reset_state()
        Motor._controller.stop()

    @staticmethod
    def move(left_orientation, left_speed, right_orientation, right_speed, duration, distance, rotation, auto_stop):
        Motor._controller.move(left_orientation, left_speed, right_orientation, right_speed, duration, distance, rotation, auto_stop)

    @staticmethod
    def move_to_target(x, y, speed, timeout):
        orientation = 'F' if y >= 0 else 'B'
        if x == 0:
            Motor._controller.move(
                left_orientation=orientation,
                left_speed=speed,
                right_orientation=orientation,
                right_speed=speed,
                duration=timeout,
                distance=y,
                rotation=None,
                auto_stop=False
            )
        else:
            R = (y*y + x*x) / (2 * abs(x))
            alpha = math.asin(y / R)
            target_distance = abs(R * alpha)
            if x > 0:
                left_speed = speed
                right_speed = speed * (R / (R + Motor.robot_width / 1000))
            else:
                right_speed = speed
                left_speed = speed * (R / (R + Motor.robot_width / 1000))
            Motor._controller.move(
                left_orientation=orientation,
                left_speed=left_speed,
                right_orientation=orientation,
                right_speed=right_speed,
                duration=timeout,
                distance=target_distance,
                rotation=None,
                auto_stop=False
            )

    @staticmethod
    def patrol():
        Motor._controller.patrol()

    @staticmethod
    def serialize():
        left_status, right_status = Motor._controller.get_motor_status()
        distance, abs_distance = Motor._controller.get_distance()
        return dict(
            status=Motor._controller.status,
            left=left_status,
            right=right_status,
            distance=distance,
            us_distances=Motor._controller.get_us_distances(),
            abs_distance=abs_distance,
        )
