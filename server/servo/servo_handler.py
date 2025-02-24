from uart import UART


class ServoHandler:

    @staticmethod
    def move(servo_id, position):
        position = int(max(0, min(100, position)))
        UART.write(f"S:M:{servo_id}:{int(position)}")

    @staticmethod
    def stop():
        UART.write("S:S")

    @staticmethod
    def configure(servo_id, min_pulse_us, max_pulse_us):
        UART.write(f"S:C:{servo_id}:{min_pulse_us}:{max_pulse_us}")
