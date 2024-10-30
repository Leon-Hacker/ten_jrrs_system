import serial
import struct
import time
from PySide6.QtCore import QThread, Signal

class PressureSensor:
    def __init__(self, port='/dev/tty.usbserial-120', baudrate=9600, address=1):
        self.port = port
        self.baudrate = baudrate
        self.address = address  # MODBUS slave address
        self.ser = None

    def open_connection(self):
        """Open the serial connection."""
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1
        )

    def close_connection(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()

    def crc16(self, data):
        """Calculate the CRC16 using the MODBUS RTU polynomial (0xA001) and return as little-endian."""
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
        request = struct.pack('>B', self.address)  # Slave address
        request += struct.pack('>B', function_code)  # Function code
        request += struct.pack('>H', start_address)  # Start address

        if function_code == 0x03:  # Read request
            request += struct.pack('>H', register_count_or_value)  # Number of registers to read
        elif function_code == 0x06:  # Write request
            request += struct.pack('>H', register_count_or_value)  # Single register value to write

        # CRC16 Calculation
        crc = self.crc16(request)
        request += crc  # Append CRC
        return request

    def send_request(self, function_code, start_address, register_count_or_value):
        """Send a MODBUS RTU request and receive the response."""
        if not self.ser or not self.ser.is_open:
            self.open_connection()

        request = self.build_modbus_request(function_code, start_address, register_count_or_value)

        # Flush input buffer to ensure no old/stale data is present before sending new request
        self.ser.reset_input_buffer()  # or self.ser.reset_input_buffer()

        self.ser.write(request)

        # Add a delay after sending the request to allow the sensor to process it
        # time.sleep(0.05)  # 50 ms delay

        # Read response depending on the function
        if function_code == 0x03:  # Read request
            response = self.ser.read(5 + 2 * register_count_or_value)  # 5 overhead bytes + 2 bytes per register
        elif function_code == 0x06:  # Write request
            response = self.ser.read(8)  # 8 bytes in response for write
        return response

    def parse_response(self, response):
        """Parse the MODBUS RTU response and validate the CRC."""
        if len(response) < 5:
            return None

        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = struct.unpack('<H', self.crc16(response[:-2]))[0]

        if received_crc != calculated_crc:
            raise ValueError("CRC mismatch")

        # Extract the data from the response (ignore address and function code)
        byte_count = response[2]
        values = []
        
        # Now, use '>h' to unpack as signed 16-bit integers
        for i in range(0, byte_count, 2):
            value = struct.unpack('>h', response[3 + i:5 + i])[0]  # Signed 16-bit integer
            values.append(value)

        return values

    def read_pressure_output(self):
        """Read the pressure/temperature output value (0x0004)."""
        pressure = self.read_register(0x0004)
        return pressure / 1000 if pressure is not None else None

    def read_register(self, address):
        """General function to read a single register."""
        response = self.send_request(0x03, address, 1)
        values = self.parse_response(response)
        return values[0] if values else None


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
