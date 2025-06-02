import serial
import struct
import time
from PySide6.QtCore import QThread, Signal
import logging
from logging.handlers import RotatingFileHandler

# Configure a logger for the pressure sensor with size-based rotation
pressuresensor_logger = logging.getLogger("PressureSensor")
pressuresensor_handler = RotatingFileHandler(
    'logs/pressuresensor.log',
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=5,
    encoding='utf-8'
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
pressuresensor_handler.setFormatter(formatter)
pressuresensor_logger.addHandler(pressuresensor_handler)
pressuresensor_logger.setLevel(logging.INFO)

class PressureSensor:
    def __init__(self, port='COM4', baudrate=9600, address=1):
        self.port = port
        self.baudrate = baudrate
        self.address = address  # MODBUS slave address
        self.ser = None
        pressuresensor_logger.info(
            "Initialized PressureSensor with port=%s, baudrate=%d, address=%d",
            self.port, self.baudrate, self.address
        )

    def open_connection(self):
        """Open the serial connection."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=1
            )
            pressuresensor_logger.info(
                "Opened serial connection on port=%s, baudrate=%d",
                self.port, self.baudrate
            )
        except serial.SerialException as e:
            pressuresensor_logger.error(
                "Failed to open serial connection on %s: %s", self.port, str(e)
            )
            raise

    def close_connection(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            pressuresensor_logger.info("Closed serial connection on port=%s", self.port)

    def crc16(self, data):
        """
        Calculate the CRC16 using the MODBUS RTU polynomial (0xA001) and return as little-endian.
        """
        crc = 0xFFFF
        for pos in data:
            crc ^= pos
            for _ in range(8):
                if crc & 0x0001:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        # Return CRC in little-endian format
        return struct.pack('<H', crc)

    def build_modbus_request(self, function_code, start_address, register_count_or_value):
        """Build a MODBUS RTU request (for both reading and writing)."""
        request = struct.pack('>B', self.address)       # Slave address
        request += struct.pack('>B', function_code)      # Function code
        request += struct.pack('>H', start_address)      # Start address

        if function_code == 0x03:  # Read request
            request += struct.pack('>H', register_count_or_value)  # Number of registers to read
        elif function_code == 0x06:  # Write request
            request += struct.pack('>H', register_count_or_value)  # Single register value to write

        # CRC16 Calculation
        crc = self.crc16(request)
        request += crc  # Append CRC

        pressuresensor_logger.debug(
            "Built MODBUS request (func=0x%02X, addr=0x%04X, value=%d): %s",
            function_code, start_address, register_count_or_value, request.hex()
        )
        return request

    def send_request(self, function_code, start_address, register_count_or_value):
        """Send a MODBUS RTU request and receive the response."""
        if not self.ser or not self.ser.is_open:
            pressuresensor_logger.debug("Serial not open. Attempting to open connection.")
            self.open_connection()

        request = self.build_modbus_request(function_code, start_address, register_count_or_value)
        self.ser.reset_input_buffer()  # Clear any stale data
        try:
            self.ser.write(request)
            pressuresensor_logger.debug("Sent request: %s", request.hex())
        except Exception as e:
            pressuresensor_logger.error("Failed to write request to serial: %s", str(e))
            raise

        # Wait for response
        if function_code == 0x03:  # Read request
            expected_length = 5 + 2 * register_count_or_value  # 5 overhead bytes + 2 bytes per register
        elif function_code == 0x06:  # Write request
            expected_length = 8  # 8 bytes in response for write
        else:
            pressuresensor_logger.error("Unsupported function code: 0x%02X", function_code)
            return None

        try:
            response = self.ser.read(expected_length)
            pressuresensor_logger.debug("Received response: %s", response.hex())
        except Exception as e:
            pressuresensor_logger.error("Failed to read response from serial: %s", str(e))
            raise

        return response

    def parse_response(self, response):
        """Parse the MODBUS RTU response and validate the CRC."""
        if len(response) < 5:
            pressuresensor_logger.warning("Response too short: %s", response.hex())
            return None

        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = struct.unpack('<H', self.crc16(response[:-2]))[0]

        if received_crc != calculated_crc:
            msg = f"CRC mismatch (received=0x{received_crc:04X}, calculated=0x{calculated_crc:04X})."
            pressuresensor_logger.error(msg)
            raise ValueError(msg)

        # Extract the data from the response (ignore address and function code)
        byte_count = response[2]
        values = []

        # Now, use '>h' to unpack as signed 16-bit integers
        for i in range(0, byte_count, 2):
            value = struct.unpack('>h', response[3 + i:5 + i])[0]  # Signed 16-bit integer
            values.append(value)

        pressuresensor_logger.debug(
            "Parsed response successfully. Byte count=%d, Values=%s",
            byte_count, values
        )
        return values

    def read_pressure_output(self):
        """
        Read the pressure/temperature output value (register address=0x0004).
        Divide by 1000 to convert to engineering units if the device documentation requires it.
        """
        raw_value = self.read_register(0x0004)
        if raw_value is not None:
            pressure = raw_value / 1000.0
            pressuresensor_logger.info("Read pressure output: %.3f", pressure)
            return pressure
        else:
            pressuresensor_logger.warning("Failed to read pressure output from register 0x0004.")
            return None

    def read_register(self, address):
        """
        General function to read a single register (function code=0x03).
        Returns the first value from the parsed response if available.
        """
        try:
            response = self.send_request(0x03, address, 1)
            if response:
                values = self.parse_response(response)
                if values:
                    reg_value = values[0]
                    pressuresensor_logger.info("Read register 0x%04X => %d", address, reg_value)
                    return reg_value
                else:
                    pressuresensor_logger.warning("No values parsed from response for register 0x%04X.", address)
            else:
                pressuresensor_logger.warning("No response received for register 0x%04X.", address)
        except Exception as e:
            pressuresensor_logger.error(
                "Error reading register 0x%04X: %s",
                address, str(e)
            )
        return None


class PressureSensorThread(QThread):
    pressure_updated = Signal(float, float)  # Signal to send pressure data to the GUI

    def __init__(self, pressure_sensor, parent=None):
        super().__init__(parent)
        self.pressure_sensor = pressure_sensor
        self.running = True

    def run(self):
        """Main loop for monitoring pressure."""
        while self.running:
            try:
                pressure = self.pressure_sensor.read_pressure_output()
                cur_time = time.time()
                if pressure is not None:
                    self.pressure_updated.emit(pressure, cur_time)
            except Exception as e:
                print(f"Error reading pressure: {e}")
            self.msleep(1000)  # Polling every second

    def stop(self):
        """Stop the thread."""
        self.running = False
        self.wait()
