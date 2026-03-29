import logging
import math
import time

from models import Config
from uart import UART, MessageOriginator, MessageType

logger = logging.getLogger(__name__)


class PicoMotor(object):
    INIT_REFRESH_INTERVAL = 2.0  # Interval at which we check the initialization status

    status = "UK"

    distance = 0.0
    abs_distance = 0.0
    rotation = 0.0
    original_rotation = None
    left_us_distance = None
    front_us_distance = None
    right_us_distance = None
    pos_x = 0
    pos_y = 0

    left_speed = 0
    left_duty = 0
    right_speed = 0
    right_duty = 0

    target_distance = None
    target_rotation = None

    max_rpm = None
    wheel_d = None
    robot_width = None

    obstacles = []

    last_init_ts = 0.0

    @staticmethod
    def setup():
        # Motor Initialization
        PicoMotor.last_init_ts = time.time()
        PicoMotor.max_rpm = Config.get("motor_max_rpm")
        PicoMotor.wheel_d = Config.get("wheel_d")
        PicoMotor.robot_width = Config.get("robot_width")
        PicoMotor.status = "OK"
        steps_per_rotation = Config.get("motor_steps_per_rotation")
        min_distance = Config.get("motor_min_distance")
        max_rpm = Config.get("motor_max_rpm")
        kp = Config.get("motor_kp")
        ki = Config.get("motor_ki")
        kd = Config.get("motor_kd")
        success = False
        for i in range(20):
            if UART.ready():
                success = True
                # Config ultrasonic sensors
                robot_us_sensor = Config.get("robot_us_sensors")
                if robot_us_sensor == "front":
                    UART.write("U:C:N:Y:N")
                elif robot_us_sensor == "front_and_side":
                    UART.write("U:C:Y:Y:Y")
                else:
                    UART.write("U:C:N:N:N")
                # Configure Motor Handler
                dead_zone = Config.get("motor_dead_zone")
                cmd = f"M:C:{steps_per_rotation}:{min_distance}:{max_rpm}:{kp}:{ki}:{kd}"
                if dead_zone is not None:
                    cmd += f":{int(dead_zone)}"
                UART.write(cmd)
                break
            time.sleep(0.1)
        if success:
            logger.info("Successfully initialized motor controller")
        else:
            logger.error("Unable to initialized motor controller")
        UART.register_consumer("motor_controller", PicoMotor, MessageOriginator.motor, MessageType.status)

    @staticmethod
    def receive_uart_message(message, originator, message_type):
        PicoMotor.left_duty = int(message[0])
        PicoMotor.left_speed = int(message[1])
        PicoMotor.right_duty = int(message[2])
        PicoMotor.right_speed = int(message[3])
        PicoMotor.distance = float(message[4]) * math.pi * PicoMotor.wheel_d / 1000
        PicoMotor.abs_distance = float(message[5]) * math.pi * PicoMotor.wheel_d
        PicoMotor.rotation = float(message[6]) * 180 * PicoMotor.wheel_d / PicoMotor.robot_width
        PicoMotor.left_us_distance = float(message[7]) if message[7] != "null" else None
        PicoMotor.front_us_distance = float(message[8]) if message[8] != "null" else None
        PicoMotor.right_us_distance = float(message[9]) if message[9] != "null" else None
        is_controller_initialized = message[10].lower() in ("y", "true")
        if not is_controller_initialized and time.time() > PicoMotor.last_init_ts + PicoMotor.INIT_REFRESH_INTERVAL:
            PicoMotor.setup()

    @staticmethod
    def stop():
        UART.write("M:S")
        # Stop patroller
        UART.write("P:0")

    @staticmethod
    def move(left_orientation, left_speed, right_orientation, right_speed, duration, distance, rotation, auto_stop):
        nb_of_revolutions = 0
        if distance is not None:
            nb_of_revolutions = 1000 * distance / (math.pi * PicoMotor.wheel_d)
        differential_nb_of_revolutions = 0
        if rotation is not None:
            differential_nb_of_revolutions = rotation * PicoMotor.robot_width / (180.0 * PicoMotor.wheel_d)
        UART.write(
            f"M:M:{left_orientation}:{int(left_speed)}:{right_orientation}:{int(right_speed)}:{nb_of_revolutions:.2f}:{differential_nb_of_revolutions:.2f}:{duration}:{auto_stop}"
        )

    @staticmethod
    def get_motor_status():
        return {"speed_rpm": PicoMotor.left_speed, "duty": PicoMotor.left_duty}, {"speed_rpm": PicoMotor.right_speed, "duty": PicoMotor.right_duty}

    @staticmethod
    def get_distance():
        return PicoMotor.distance, PicoMotor.abs_distance

    @staticmethod
    def get_us_distances():
        return PicoMotor.left_us_distance, PicoMotor.front_us_distance, PicoMotor.right_us_distance

    @staticmethod
    def get_position():
        return PicoMotor.pos_x, PicoMotor.pos_y, PicoMotor.rotation

    @staticmethod
    def get_obstacles():
        return PicoMotor.obstacles

    @staticmethod
    def patrol():
        timeout = 300
        speed = Config.get("motor_patrol_speed")
        UART.write(f"P:{speed}:{timeout}:false")

