import copy
import logging
import math
import time
from servo.servo_handler import ServoHandler
from uart import UART, MessageOriginator, MessageType

logger = logging.getLogger(__name__)

CLAW = "claw"
WRIST = "wrist"
FOREARM = "forearm"
SHOULDER = "shoulder"

SERVOS_CONFIG = {
    CLAW: {
        "id": 5,
        "min_pulse_us": 1000,
        "max_pulse_us": 2000,
        "max_angle": 180,
        "speed": 0.11, # Sec / 60 deg
        "max_speed": 100,  # Percent / sec
    },
    WRIST: {
        "id": 4,
        "min_pulse_us": 500,
        "max_pulse_us": 2500,
        "max_angle": 180,
        "speed": 0.15, # Sec / 60 deg
        "max_speed": 100,  # Percent / sec
    },
    FOREARM: {
        "id": 3,
        "min_pulse_us": 500,
        "max_pulse_us": 2500,
        "max_angle": 180,
        "speed": 0.15, # Sec / 60 deg
        "max_speed": 100,  # Percent / sec
    },
    SHOULDER: {
        "id": 2,
        "min_pulse_us": 500,
        "max_pulse_us": 2500,
        "max_angle": 270,
        "speed": 0.11, # Sec / 60 deg
        "max_speed": 100,  # Percent / sec
    },
}

DEFAULT_EXCLUSION_ZONES = [
    {
        FOREARM: [100, 180],
        SHOULDER: [127, 270]
    },
    {
        FOREARM: [145, 180],
        SHOULDER: [0, 34]
    },
    {
        FOREARM: [145, 180],
        SHOULDER: [36, 180]
    },
    {
        FOREARM: [171, 180],
        SHOULDER: [35, 35]
    },
]
#EXCLUSION_ZONES = Config.get("exclusion_zones", DEFAULT_EXCLUSION_ZONES)
EXCLUSION_ZONES = DEFAULT_EXCLUSION_ZONES

PRESET_POSITIONS = {
    "zero": {
        "name": "Zero",
        "moves": [
            {"id": FOREARM, "angle": 60},
            {"id": WRIST, "angle": 60},
            {"id": SHOULDER, "angle": 35},
        ]
    },
    "backup_camera": {
        "name": "Back up Camera",
        "moves": [
            {"id": FOREARM, "angle": 30},
            {"id": WRIST, "angle": 165},
            {"id": SHOULDER, "angle": 35},
        ]
    },
    "pickup": {
        "name": "Pickup From Floor",
        "moves": [
            {"id": SHOULDER, "angle": 35},
            {"id": WRIST, "angle": 25},
            {"id": FOREARM, "angle": 170},
        ]
    },
    "grab": {
        "name": "Grab From Floor",
        "moves": [
            {"id": SHOULDER, "angle": 35},
            {"id": WRIST, "angle": 170},
            {"id": FOREARM, "angle": 110},
        ]
    },
    "drop": {
        "name": "Drop on platform",
        "moves": [
            {"id": FOREARM, "angle": 30},
            {"id": WRIST, "angle": 165},
            {"id": SHOULDER, "angle": 215},
        ]
    },
}

class Arm(object):
    status = "UK"
    position = {
        CLAW: 0,
        WRIST: 0,
        FOREARM: 0,
        SHOULDER: 0,
    }

    @staticmethod
    def setup():
        for servo_config in SERVOS_CONFIG.values():
            ServoHandler.configure(
                servo_id=servo_config["id"],
                min_pulse_us=servo_config["min_pulse_us"],
                max_pulse_us=servo_config["max_pulse_us"],
                max_speed=servo_config["max_speed"],
            )
        Arm.move_to_position("backup_camera")
        Arm.move_servo_to_position(CLAW, SERVOS_CONFIG[CLAW]['max_angle'])
        Arm.status = "OK"
        UART.register_consumer("arm_controller", Arm, MessageOriginator.servo, MessageType.status)
        logger.info("Successfully initialized servo controller")

    @staticmethod
    def receive_uart_message(message, originator, message_type):
        servo_id_to_limb = {s["id"]: limb for limb, s in SERVOS_CONFIG.items()}
        servo_nb = 0
        while len(message) > servo_nb * 3:
            offset = servo_nb * 3
            servo_id = int(message[offset])
            is_initialized = message[offset + 1].lower() == "y"
            position = message[offset + 2]
            position = float(position) if position != 'null' else None
            servo_nb += 1
            if servo_id in servo_id_to_limb:
                limb = servo_id_to_limb[servo_id]
                servo_config = SERVOS_CONFIG[limb]
                if position is not None:
                    Arm.position[limb] = position * servo_config["max_angle"] / 100.0
                if not is_initialized:
                    logger.info("Successfully re-initialized servo controller")
                    ServoHandler.configure(
                        servo_id=servo_config["id"],
                        min_pulse_us=servo_config["min_pulse_us"],
                        max_pulse_us=servo_config["max_pulse_us"],
                        max_speed=servo_config["max_speed"],
                    )

    @staticmethod
    def _in_exclusion_zone(id, angle, position=None):
        if position is None:
            position = Arm.position
        for exclusion_zone in EXCLUSION_ZONES:
            if id in exclusion_zone:
                if angle < exclusion_zone.get(id)[0] or angle > exclusion_zone.get(id)[1]:
                    continue
                else:
                    all_match = True
                    for other_id in [i for i in exclusion_zone.keys() if i != id]:
                        if position[other_id] < exclusion_zone[other_id][0] or position[other_id] > exclusion_zone[other_id][1]:
                            all_match = False
                    if all_match:
                        return True
        return False

    @staticmethod
    def _get_servo_range(id):
        servo_config = SERVOS_CONFIG.get(id)
        position = Arm.position
        for exclusion_zone in EXCLUSION_ZONES:
            if id in exclusion_zone:
                all_match = True
                for other_id in [i for i in exclusion_zone.keys() if i != id]:
                    if position[other_id] < exclusion_zone[other_id][0] or position[other_id] > exclusion_zone[other_id][1]:
                        all_match = False
                if all_match and False:
                    if position[id] < exclusion_zone[id][0]:
                        return [0, exclusion_zone[id][0]]
                    elif position[id] > exclusion_zone[id][1]:
                        return [exclusion_zone[id][1], servo_config["max_angle"]]
                    # In exclusion zone, no move possible
                    return None
        return [0, servo_config["max_angle"]]

    @staticmethod
    def get_ids():
        return list(SERVOS_CONFIG.keys())

    @staticmethod
    def get_position_ids():
        return list(PRESET_POSITIONS.keys())

    @staticmethod
    def stop():
        for servo_config in SERVOS_CONFIG.values():
            ServoHandler.stop_servo(servo_config.get("id"))

    @staticmethod
    def stop_servo(id):
        servo_config = SERVOS_CONFIG.get(id)
        if servo_config is None:
            return False, f"Unknown servo ID: {id}"
        ServoHandler.stop_servo(servo_config.get("id"))

    @staticmethod
    def move(id, speed, lock_wrist=False):
        servo_config = SERVOS_CONFIG.get(id)
        if servo_config is None:
            return False, f"Unknown servo ID: {id}"

        servo_range = Arm._get_servo_range(id)
        if servo_range is not None:
            target_position = servo_range[1] if speed > 0 else servo_range[0]
            ServoHandler.move(servo_config.get("id"), target_position, abs(speed))
            return True, "Success"
        else:
            message = "{id} is in exclusion zone, no move possible"
            logger.warning(message)
            return False, message

    @staticmethod
    def move_servo_to_position(id, angle, wait=True, lock_wrist=False):
        logger.info(f"Moving servo {dict(id=id, angle=angle, wait=wait, lock_wrist=lock_wrist)}")
        servo_config = SERVOS_CONFIG.get(id)
        if servo_config is None:
            return False, f"Unknown servo ID: {id}"

        max_angle = servo_config.get("max_angle")
        if angle < 0 or angle > max_angle:
            message = f"Invalid angle: {angle} for {id}"
            logger.warning(message)
            return False, message

        if Arm._in_exclusion_zone(id, angle):
            message = f"Moving to an exclusion zone for {id}"
            logger.warning(message)
            return False, message

        if id == FOREARM and lock_wrist:
            forearm_angle = Arm.position[FOREARM]
            wrist_angle = Arm.position[WRIST]
            step = int(math.copysign(1, angle - forearm_angle))
            for i in range(int(abs(angle - forearm_angle))):
                Arm.move_servo_to_position(id=FOREARM, angle=forearm_angle + (i + 1) * step, wait=wait, lock_wrist=False)
                Arm.move_servo_to_position(id=WRIST, angle=wrist_angle - (i + 1) * step, wait=wait, lock_wrist=False)
        else:
            ServoHandler.move(servo_config.get("id"), angle * 100 / max_angle)

            if wait:
                speed = servo_config.get('speed')
                time.sleep(1.5 * speed * abs(Arm.position[id] - angle) / 60)
            Arm.position[id] = angle
        return  True, "Success"

    @staticmethod
    def move_to_position(position_id, lock_wrist=False):
        position = PRESET_POSITIONS.get(position_id)
        if position is None:
            message = f"Unknown position ID: {position_id}"
            logger.warning(message)
            return False, message

        # Lock wrist?
        move_by_id = {move.get('id'): move.get('angle') for move in position.get('moves')}
        if lock_wrist and WRIST in move_by_id and FOREARM in move_by_id:
            moves = []
            wrist_angle = move_by_id.get(WRIST) + move_by_id.get(FOREARM) - Arm.position.get(FOREARM)
            # First adjust wrist
            moves.append(dict(id=WRIST, angle=wrist_angle))
            moves.append(dict(id=FOREARM, angle=move_by_id.get(FOREARM), lock_wrist=True))
            if SHOULDER in move_by_id:
                moves.append(dict(id=SHOULDER, angle=move_by_id.get(SHOULDER)))
        else:
            moves = copy.deepcopy(position.get("moves"))

        # Try to re-arrange moves to avoid exclusion zones
        servo_position = copy.deepcopy(Arm.position)
        sorted_moves = []
        nb_of_moves = 0
        while len(moves) > 0:
            for i in range(len(moves)):
                move = moves.pop(0)
                if not Arm._in_exclusion_zone(move.get("id"), move.get("angle"), servo_position):
                    servo_position[move.get('id')] = move.get('angle')
                    sorted_moves.append(move)
                else:
                    moves.append(move)
            # No new moves found?
            if len(sorted_moves) == nb_of_moves:
                message = "Moving to an exclusion zone"
                logger.warning(message)
                return False, message
            nb_of_moves = len(sorted_moves)

        for move in sorted_moves:
            success, message = Arm.move_servo_to_position(id=move.get("id"), angle=move.get("angle"), lock_wrist=move.get('lock_wrist', False))
            if not success:
                logger.warning(message)
                return False, message

        return  True, "Success"

    @staticmethod
    def serialize():
        return {
            "position": Arm.position,
            "ids": Arm.get_ids(),
            "position_ids": Arm.get_position_ids(),
            "config": SERVOS_CONFIG
        }
