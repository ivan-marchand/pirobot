from threading import Timer

try:
    import RPi.GPIO as GPIO
except:
    import sys
    import fake_rpi
    sys.modules['RPi'] = fake_rpi.RPi
    sys.modules['RPi.GPIO'] = fake_rpi.RPi.GPIO
    import RPi.GPIO as GPIO

LEFT_LIGHT_PIN = 17
RIGHT_LIGHT_PIN = 16
ARM_LIGHT_PIN = 21
BLINK_DURATION = 0.5
NB_OF_BLINKS = 5


class Light(object):
    status = "UK"
    left_on = False
    right_on = False
    arm_on = False

    Timers = []

    @staticmethod
    def _cancel_event():
        for timer in Light.Timers:
            timer.cancel()
        Light.Timers = []

    @staticmethod
    def _schedule_event(delay, function, args=[], kwargs={}):
        timer = Timer(delay, function, args, kwargs)
        timer.start()
        Light.Timers.append(timer)

    @staticmethod
    def setup():
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(LEFT_LIGHT_PIN, GPIO.OUT)
        GPIO.setup(RIGHT_LIGHT_PIN, GPIO.OUT)
        GPIO.setup(ARM_LIGHT_PIN, GPIO.OUT)
        GPIO.output(LEFT_LIGHT_PIN, GPIO.LOW)
        GPIO.output(RIGHT_LIGHT_PIN, GPIO.LOW)
        GPIO.output(ARM_LIGHT_PIN, GPIO.LOW)
        Light.left_on = False
        Light.right_on = False
        Light.arm_on = False
        Light.status = "OK"

    @staticmethod
    def set_front_light(left_on, right_on):
        Light._cancel_event()
        Light.set(left_on=left_on, right_on=right_on)

    @staticmethod
    def set_light(left_on, right_on, arm_on):
        Light._cancel_event()
        Light.set(left_on=left_on, right_on=right_on, arm_on=arm_on)

    @staticmethod
    def set(left_on=None, right_on=None, arm_on=None):
        if left_on is not None:
           Light.left_on = left_on
        if right_on is not None:
            Light.right_on = right_on
        if arm_on is not None:
            Light.arm_on = arm_on
        Light._set()

    @staticmethod
    def _set():
        GPIO.output(LEFT_LIGHT_PIN, GPIO.HIGH if Light.left_on else GPIO.LOW)
        GPIO.output(RIGHT_LIGHT_PIN, GPIO.HIGH if Light.right_on else GPIO.LOW)
        GPIO.output(ARM_LIGHT_PIN, GPIO.HIGH if Light.arm_on else GPIO.LOW)

    @staticmethod
    def toggle_front_light():
        Light._cancel_event()
        Light.toggle(True, True)

    @staticmethod
    def toggle(left_on, right_on):
        is_on = Light.left_on or Light.right_on
        Light.set(left_on and not is_on, right_on and not is_on)

    @staticmethod
    def toggle_arm_light():
        Light._cancel_event()
        Light.set(arm_on=not Light.arm_on)

    @staticmethod
    def blink(left_on=None, right_on=None):
        time = 0
        if left_on or right_on:
            for i in range(NB_OF_BLINKS * 2):
                Light._schedule_event(time, Light.toggle, kwargs=dict(left_on=left_on, right_on=right_on))
                time += BLINK_DURATION
        Light._schedule_event(time, Light.set_front_light, kwargs=dict(left_on=False, right_on=False))
        Light.set(Light.left_on, Light.right_on, Light.arm_on)

    @staticmethod
    def serialize():
        return {
            'status': Light.status,
            'left_on': Light.left_on,
            'right_on': Light.right_on,
            'arm_on': Light.arm_on
        }

