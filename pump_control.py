import serial
import struct
import crcmod
import time
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

class PumpControl:
    def __init__(self, port='COM13', baudrate=9600, address=1):
        """Initialize the PumpControl class with serial settings and Modbus address."""
        self.port = port
        self.baudrate = baudrate
        self.address = address  # Modbus slave address
        self.ser = None
        self.crc16 = crcmod.predefined.mkCrcFun('modbus')

    def open_connection(self):
        """Open the serial connection to the pump."""
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1  # Timeout set to 1 seconds
        )

    def close_connection(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()

    def calculate_crc(self, data):
        """Calculate CRC16 for the Modbus RTU frame."""
        return self.crc16(data)

    def read_registers(self, start_address, num_registers):
        """Read Modbus holding registers."""
        function_code = 0x03  # Read holding registers
        request = struct.pack('>B B H H', self.address, function_code, start_address, num_registers)
        crc = self.calculate_crc(request)
        request += struct.pack('<H', crc)

        self.ser.reset_input_buffer()
        self.ser.write(request)

        # Expected response length
        response_length = 1 + 1 + 1 + 2 * num_registers + 2
        response = self.ser.read(response_length)

        if len(response) < response_length:
            print("Incomplete response received.")
            return None

        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self.calculate_crc(response[:-2])
        if received_crc != calculated_crc:
            print(f"CRC error: received {received_crc:04X}, expected {calculated_crc:04X}")
            return None

        # Extract registers from response
        data = response[3:-2]
        registers = struct.unpack('>' + 'H' * num_registers, data)
        return registers

    def write_pump_status(self, status):
        """Write the pump status (start, stop, or pause) to the control register."""
        function_code = 0x06  # Write single register function code
        address = 5  # Register address 40006, 0-based is 5
        request = struct.pack('>B B H H', self.address, function_code, address, status)
        crc = self.calculate_crc(request)
        request += struct.pack('<H', crc)

        self.ser.reset_input_buffer()
        self.ser.write(request)

        # Expected response length: 8 bytes
        response = self.ser.read(8)
        if len(response) < 8:
            print("Incomplete response received.")
            return False

        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self.calculate_crc(response[:-2])
        if received_crc != calculated_crc:
            print(f"CRC error: received {received_crc:04X}, expected {calculated_crc:04X}")
            return False

        return True

    def start_pump(self):
        """Start the pump by writing the start status to the control register."""
        if self.write_pump_status(0x0500):
            print("Pump started successfully.")
        else:
            print("Failed to start the pump.")

    def stop_pump(self):
        """Stop the pump by writing the stop status to the control register."""
        if self.write_pump_status(0x0000):
            print("Pump stopped successfully.")
        else:
            print("Failed to stop the pump.")

    def pause_pump(self):
        """Pause the pump by writing the pause status to the control register."""
        if self.write_pump_status(0x0600):
            print("Pump paused successfully.")
        else:
            print("Failed to pause the pump.")

    def read_pump_parameters(self):
        """Read the pump's pressure, flow rate, and stroke in one go."""
        # Read from address 50 to 54 (includes flow, pressure, and stroke)
        parameters = self.read_registers(50, 6)  # Read 6 registers (2 for each float value)
        if parameters:
            # Extract values
            flow = struct.unpack('>f', struct.pack('>HH', parameters[0], parameters[1]))[0]
            pressure = struct.unpack('>f', struct.pack('>HH', parameters[2], parameters[3]))[0]
            stroke = struct.unpack('>f', struct.pack('>HH', parameters[4], parameters[5]))[0]
            return flow, pressure, stroke
        return None, None, None

    def read_pump_status(self):
        """Read the current run state of the pump (start, pause, stop)."""
        # Pump status register is at 40006, so 40006 - 40001 = 5 (0-based)
        request2 = struct.pack('>B B H H', self.address, 0x03, 5, 1)
        crc2 = self.calculate_crc(request2)
        request2 += struct.pack('<H', crc2)
        self.ser.reset_input_buffer()
        self.ser.write(request2)

        response_length2 = 1 + 1 + 1 + 2 + 2
        response2 = self.ser.read(response_length2)

        if len(response2) < response_length2:
            print("Incomplete response received.")
            return None
        
        # Validate CRC
        received_crc2 = struct.unpack('<H', response2[-2:])[0]
        calculated_crc2 = self.calculate_crc(response2[:-2])

        if received_crc2 != calculated_crc2:
            print(f"CRC error: received {received_crc2:04X}, expected {calculated_crc2:04X}")
            return None
        
        # Extract the first byte of data to determine the pump status
        status_byte = response2[3]

        # Interpret the pump status
        if status_byte == 0x05:
            return "start"
        elif status_byte == 0x06:
            return "pause"
        elif status_byte == 0x00:
            return "stop"
        else:
            print(f"Unknown status byte: {status_byte:02X}")
            return None

    def set_stroke(self, stroke_value):
        """Set the stroke of the pump (range 0-100%)."""
        if not 0 <= stroke_value <= 100:
            print("Invalid stroke value. Must be between 0 and 100.")
            return False

        # Convert stroke value to a 32-bit float and split into two 16-bit registers
        stroke_registers = struct.unpack('>HH', struct.pack('>f', stroke_value))

        # Write to itinerary (address 40055, 0-based is 54)
        return self.write_registers(54, stroke_registers)

    def write_registers(self, start_address, values):
        """Write multiple Modbus holding registers."""
        function_code = 0x10  # Write multiple registers
        num_registers = len(values)
        byte_count = num_registers * 2
        request = struct.pack('>B B H H B', self.address, function_code, start_address, num_registers, byte_count)
        request += struct.pack('>' + 'H' * num_registers, *values)

        crc = self.calculate_crc(request)
        request += struct.pack('<H', crc)

        self.ser.reset_input_buffer()
        self.ser.write(request)

        response = self.ser.read(8)
        if len(response) < 8:
            print("Incomplete response received.")
            return False

        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self.calculate_crc(response[:-2])
        if received_crc != calculated_crc:
            print(f"CRC error: received {received_crc:04X}, expected {calculated_crc:04X}")
            return False

        return True

    def read_pressure(self):
        """Read the real-time pressure."""
        # Pressure address is 40053, so 40053 - 40001 = 52 (0-based)
        registers = self.read_registers(52, 2)
        if registers:
            pressure = struct.unpack('>f', struct.pack('>HH', *registers))[0]
            return pressure
        return None

    def read_flow(self):
        """Read the instantaneous flow."""
        # Flow address is 40051, so 40051 - 40001 = 50 (0-based)
        registers = self.read_registers(50, 2)
        if registers:
            flow = struct.unpack('>f', struct.pack('>HH', *registers))[0]
            return flow
        return None

    def read_stroke(self):
        """Read the current stroke (itinerary) of the pump."""
        # Itinerary address is 40055, so 40055 - 40001 = 54 (0-based)
        stroke_registers = self.read_registers(54, 2)
        if stroke_registers:
            stroke_value = struct.unpack('>f', struct.pack('>HH', *stroke_registers))[0]
            return stroke_value
        return None


class PumpControlThread(QThread):
    pressure_updated = Signal(float)  # Signal to update pressure in the GUI
    flow_updated = Signal(float)      # Signal to update flow in the GUI
    stroke_updated = Signal(float)    # Signal to update stroke in the GUI
    status_updated = Signal(str)      # Signal to update pump status in the GUI

    def __init__(self, pump_control, parent=None):
        """Initialize the PumpControlThread class."""
        super().__init__(parent)
        self.pump_control = pump_control
        self.running = True
        self.mutex = QMutex()  # Ensure thread-safe operation

    def run(self):
        """Continuously monitor pump parameters in the background."""
        while self.running:
            with QMutexLocker(self.mutex):
                try:
                    flow, pressure, stroke = self.pump_control.read_pump_parameters()
                    if pressure is not None:
                        self.pressure_updated.emit(pressure)
                    if flow is not None:
                        self.flow_updated.emit(flow)
                    else:
                        self.flow_updated.emit(-1)
                    if stroke is not None:
                        self.stroke_updated.emit(stroke)
                    self.msleep(50)
                    status = self.pump_control.read_pump_status()
                    if status is not None:
                        self.status_updated.emit(status)
                    self.msleep(50)
                except Exception as e:
                    print(f"Error reading pump parameters: {e}")
            self.msleep(900)  # Poll every second

    def set_stroke(self, stroke_value):
        """Set the stroke of the pump in a thread-safe manner."""
        with QMutexLocker(self.mutex):
            try:
                success = self.pump_control.set_stroke(stroke_value)
                if success:
                    print(f"Stroke set to {stroke_value}%")
                else:
                    print(f"Failed to set stroke to {stroke_value}%")
            except Exception as e:
                print(f"Error setting stroke: {e}")

    def start_pump(self):
        """Start the pump in a thread-safe manner."""
        with QMutexLocker(self.mutex):
            try:
                self.pump_control.start_pump()
            except Exception as e:
                print(f"Error starting pump: {e}")

    def stop_pump(self):
        """Stop the pump in a thread-safe manner."""
        with QMutexLocker(self.mutex):
            try:
                self.pump_control.stop_pump()
            except Exception as e:
                print(f"Error stopping pump: {e}")

    def pause_pump(self):
        """Pause the pump in a thread-safe manner."""
        with QMutexLocker(self.mutex):
            try:
                self.pump_control.pause_pump()
            except Exception as e:
                print(f"Error pausing pump: {e}")

    def stop(self):
        """Stop the thread."""
        self.running = False
        self.wait()

