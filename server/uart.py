from enum import Enum
import asyncio
import logging
import serial
import threading

from models import Config
from logger import RobotLogger

logger = logging.getLogger(__name__)


class MessageOriginator(Enum):
    motor = "M"
    battery = "B"
    servo = "S"


class MessageType(Enum):
    status = "S"


class UART(object):
    consumers = {}
    uart_handler = None
    refresh_interval = 1

    class ConsumerConfig(object):
        def __init__(self, name, consumer, originator, message_type):
            self.name = name
            self.consumer = consumer
            self.originator = originator
            self.message_type = message_type

    def __init__(self, port, baudrate):
        self.read_buffer = ""
        self.write_buffer = ""
        self.port = port
        self.baudrate = baudrate
        self.write_buffer_lock = threading.Lock()
        self.has_writer = threading.Event()
        self.loop = asyncio.get_event_loop()
        self.serial = None
        self.connect()
        if Config.get("auto_uart_reconnect"):
            self.loop.call_soon(self.monitor_connection)

    def monitor_connection(self):
        if self.serial is None or not self.serial.is_open:
            logger.info("Connection lost, reconnecting...")
            self.connect()
        self.loop.call_later(UART.refresh_interval, self.monitor_connection)

    def connect(self):
        try:
            self.serial = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0,
            )
        except:
            logger.error("Unable to open serial port", exc_info=True)
            if self.serial is not None:
                self.serial.close()
                self.serial = None
        else:
            self.loop.add_reader(self.serial.fileno(), self.data_received)

    def data_received(self):
        try:
            if not self.serial.is_open:
                self.loop.remove_reader(self.serial.fileno())
            else:
                self.read_buffer += self.serial.read(1024).decode()
                while len(self.read_buffer) > 0:
                    i = self.read_buffer.find("\n")
                    if i >= 0:
                        line = self.read_buffer[:i + 1]
                        self.read_buffer = self.read_buffer[i + 1:]
                        message = line[:-1]
                        self.dispatch_uart_message(message)
                        RobotLogger.log_message("UART", "R", message)
                    elif self.serial.in_waiting == 0:
                        break
                    else:
                        self.read_buffer += self.serial.read(1024).decode()
        except:
            logger.error("Unable to read data sent on serial port", exc_info=True)
            self.loop.remove_reader(self.serial.fileno())
            self.serial.close()

    def write_data(self):
        self.write_buffer_lock.acquire()
        self.has_writer.set()
        data = self.write_buffer
        self.write_buffer = ""
        self.write_buffer_lock.release()

        # Write data to serial port
        bytes_writen = self.serial.write(data.encode())

        # All data writen?
        if bytes_writen < len(data):
            data = data[:bytes_writen]
        else:
            data = ""

        self.write_buffer_lock.acquire()
        self.write_buffer = data + self.write_buffer
        # Any data left to write?
        if len(self.write_buffer) == 0:
            self.loop.remove_writer(self.serial.fileno())
            self.has_writer.clear()
        self.write_buffer_lock.release()

    def _write(self, data):
        self.write_buffer_lock.acquire()
        self.write_buffer += data

        if not self.has_writer.is_set():
            self.loop.add_writer(self.serial.fileno(), self.write_data)
        self.write_buffer_lock.release()

    def dispatch_uart_message(self, message):
        message_parts = message.split(':')
        originator = message_parts[0]
        message_type = message_parts[1]
        # Received keepalive message?
        if originator == "K":
            UART.write("K:OK")
        for consumer_config in UART.consumers.values():
            if consumer_config.originator is not None and consumer_config.originator.value != originator:
                continue
            if consumer_config.message_type is not None and consumer_config.message_type.value != message_type:
                continue
            consumer_config.consumer.receive_uart_message(message_parts[2:], originator, message_type)

    @staticmethod
    def register_consumer(name, consumer, originator=None, message_type=None):
        UART.consumers[name] = UART.ConsumerConfig(
            name=name, consumer=consumer, originator=originator, message_type=message_type
        )

    @staticmethod
    def unregister_consumer(name):
        del UART.consumers[name]

    @staticmethod
    def ready():
        return UART.uart_handler is not None

    @staticmethod
    def open():
        if UART.uart_handler is None:
            try:
                UART.uart_handler = UART(port=Config.get("uart_port"), baudrate=Config.get("uart_baudrate"))
            except:
                logger.error("Unable to open serial port", exc_info=True)

    @staticmethod
    def write(data):
        try:
            message = data + "\n"
            if UART.uart_handler is not None and UART.uart_handler.serial is not None:
                UART.uart_handler._write(data=message)
                RobotLogger.log_message("UART", "S", data)
            else:
                logger.warning("Unable to send serial message, the port is not opened")
        except:
            logger.error("Unable to send serial message", exc_info=True)
