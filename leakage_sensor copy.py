from PySide6.QtCore import QThread, Signal
import serial
import struct
import time
import logging
from logging.handlers import RotatingFileHandler

# Configure a logger for the leakage sensor with size-based rotation
leakage_logger = logging.getLogger("LeakageSensor")
leakage_handler = RotatingFileHandler(
    'logs/leakage_sensor.log',
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=5,
    encoding='utf-8'
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
leakage_handler.setFormatter(formatter)
leakage_logger.addHandler(leakage_handler)
leakage_logger.setLevel(logging.INFO)

class LeakageSensor:
    def __init__(self, port='/dev/tty.usbserial-120', baudrate=9600, address=1):
        self.port = port
        self.baudrate = baudrate
        self.address = address  # MODBUS address of the device
        self.ser = None

    def open_connection(self):
        """Open the serial connection to the sensor."""
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1  # Timeout for the serial read
        )

    def close_connection(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()

    def crc16(self, data: bytes):
        """Calculate the CRC-16 for the MODBUS RTU protocol."""
        crc = 0xFFFF
        for pos in data:
            crc ^= pos
            for _ in range(8):
                if (crc & 0x0001):
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return crc

    def build_modbus_request(self, function_code, start_address, register_count):
        """Build the MODBUS RTU request."""
        request = struct.pack('>B', self.address)
        request += struct.pack('>B', function_code)
        request += struct.pack('>H', start_address)
        request += struct.pack('>H', register_count)
        
        # CRC16 Calculation
        crc = self.crc16(request)
        request += struct.pack('<H', crc)
        return request

    def send_request(self, function_code, start_address, register_count):
        """Send a MODBUS RTU request and read the response."""
        if not self.ser or not self.ser.is_open:
            self.open_connection()

        # Build and send request
        request = self.build_modbus_request(function_code, start_address, register_count)
        self.ser.write(request)

        # Add delay to allow sensor time to process the command
        time.sleep(0.05)  # 50 ms delay

        # Read the response (adjust byte count based on response)
        response = self.ser.read(7 + 2 * register_count)
        return response

    def parse_response(self, response):
        """Parse the MODBUS RTU response."""
        if len(response) < 5:
            return None

        # CRC Verification
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self.crc16(response[:-2])
        if received_crc != calculated_crc:
            raise ValueError("CRC mismatch")

        # Extract data (skip address and function code)
        byte_count = response[2]
        values = []
        for i in range(0, byte_count, 2):
            value = struct.unpack('>H', response[3 + i:5 + i])[0]
            values.append(value)

        return values

    def read_leakage_status(self):
        """Read the leakage sensor status."""
        # Function code 0x04 (Read Input Registers), address 0x0000, and read 1 register
        response = self.send_request(function_code=0x04, start_address=0x0000, register_count=1)
        values = self.parse_response(response)
        if values:
            return values[0]
        return None


class LeakageSensorThread(QThread):
    # Signal to send leak detection status to the main GUI
    leak_status_signal = Signal(bool)  # True for leak detected, False for no leak

    def __init__(self, leakage_sensor, parent=None):
        super().__init__(parent)
        self.leakage_sensor = leakage_sensor
        self.running = True

    def run(self):
        """Thread to continuously monitor the leakage sensor status."""
        while self.running:
            try:
                status = self.leakage_sensor.read_leakage_status()
                # 0 means no leak, 1 means leak detected
                leak_detected = (status == 1)
                self.leak_status_signal.emit(leak_detected)
            except Exception as e:
                print(f"Error reading leakage sensor: {e}")
            self.msleep(200)  # Polling every second

    def stop(self):
        """Stop the thread."""
        self.running = False
        self.wait()