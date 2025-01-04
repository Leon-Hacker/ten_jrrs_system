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
        """
        Initialize the leakage sensor with port, baud rate, and MODBUS address.
        """
        self.port = port
        self.baudrate = baudrate
        self.address = address  # MODBUS address of the device
        self.ser = None
        leakage_logger.info(
            "Initialized LeakageSensor with port=%s, baudrate=%d, address=%d",
            self.port, self.baudrate, self.address
        )

    def open_connection(self):
        """Open the serial connection to the sensor."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=1  # Timeout for the serial read
            )
            leakage_logger.info("Opened serial connection on %s with baudrate %d", self.port, self.baudrate)
        except serial.SerialException as e:
            leakage_logger.error("Failed to open serial connection on %s: %s", self.port, str(e))
            raise

    def close_connection(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            leakage_logger.info("Closed serial connection on %s", self.port)

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
        """
        Build the MODBUS RTU request for reading input registers (function=0x04) 
        or any other function code if extended in future.
        """
        request = struct.pack('>B', self.address)       # Slave address
        request += struct.pack('>B', function_code)     # Function code
        request += struct.pack('>H', start_address)     # Start address
        request += struct.pack('>H', register_count)    # Number of registers
        
        # CRC16 Calculation
        crc_value = self.crc16(request)
        request += struct.pack('<H', crc_value)
        leakage_logger.debug(
            "Built MODBUS request (func=0x%02X, addr=0x%04X, count=%d): %s",
            function_code, start_address, register_count, request.hex()
        )
        return request

    def send_request(self, function_code, start_address, register_count):
        """
        Send a MODBUS RTU request and read the response.
        For example, function_code=0x04 for reading input registers.
        """
        if not self.ser or not self.ser.is_open:
            leakage_logger.debug("Serial not open. Attempting to open connection.")
            self.open_connection()

        # Build and send request
        request = self.build_modbus_request(function_code, start_address, register_count)
        try:
            self.ser.write(request)
            leakage_logger.debug("Sent request: %s", request.hex())
        except Exception as e:
            leakage_logger.error("Error writing request to serial: %s", str(e))
            raise

        # Small delay for sensor to process the command
        time.sleep(0.05)  # 50 ms delay

        # Calculate expected response length
        # For function 0x04 (Read Input Registers): 
        #   header(3 bytes) + data(2*register_count) + CRC(2 bytes)
        expected_length = 3 + (2 * register_count) + 2
        try:
            response = self.ser.read(expected_length)
            leakage_logger.debug("Received response: %s", response.hex())
        except Exception as e:
            leakage_logger.error("Error reading response from serial: %s", str(e))
            raise

        return response

    def parse_response(self, response):
        """Parse the MODBUS RTU response and validate the CRC."""
        if len(response) < 5:
            leakage_logger.warning("Response too short: %s", response.hex())
            return None

        # Extract last two bytes for CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self.crc16(response[:-2])
        if received_crc != calculated_crc:
            msg = f"CRC mismatch (received=0x{received_crc:04X}, calculated=0x{calculated_crc:04X})"
            leakage_logger.error(msg)
            raise ValueError(msg)

        # Byte count is in the 3rd byte of the response
        byte_count = response[2]
        if len(response) < 3 + byte_count + 2:
            leakage_logger.warning("Mismatch in reported byte_count vs actual response length.")
            return None

        # Extract data (skip slave address=1 byte, function code=1 byte, byte_count=1 byte)
        values = []
        for i in range(0, byte_count, 2):
            value = struct.unpack('>H', response[3 + i:5 + i])[0]
            values.append(value)

        leakage_logger.debug("Parsed values: %s", values)
        return values

    def read_leakage_status(self):
        """
        Read the leakage sensor status (function code 0x04).
        This sensor's leakage status might be stored in a single input register at address 0x0000.
        """
        try:
            response = self.send_request(function_code=0x04, start_address=0x0000, register_count=1)
            values = self.parse_response(response)
            if values:
                leakage_logger.info("Leakage status read successfully: %d", values[0])
                return values[0]
            else:
                leakage_logger.warning("No data received for leakage status.")
                return None
        except Exception as e:
            leakage_logger.error("Error reading leakage status: %s", str(e))
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
            self.msleep(250)  # Polling every second

    def stop(self):
        """Stop the thread."""
        self.running = False
        self.wait()