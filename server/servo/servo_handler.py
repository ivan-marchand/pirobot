from uart import UART


class ServoHandler:

    @staticmethod
    def move(servo_id, position, speed=None):
        position = float(max(0, min(100, position)))
        if speed is None:
            UART.write(f"S:M:{servo_id}:{position}")
        else:
            UART.write(f"S:M:{servo_id}:{position}:{speed}")

    @staticmethod
    def stop_servo(servo_id):
        UART.write(f"S:SS:{servo_id}")

    @staticmethod
    def stop():
        UART.write("S:S")

    @staticmethod
    def configure(servo_id, min_pulse_us, max_pulse_us, max_speed=None):
        if max_speed is None:
            UART.write(f"S:C:{servo_id}:{min_pulse_us}:{max_pulse_us}")
        else:
            UART.write(f"S:C:{servo_id}:{min_pulse_us}:{max_pulse_us}:{max_speed}")
