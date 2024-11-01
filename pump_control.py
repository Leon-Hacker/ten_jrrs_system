import serial
import struct
import crcmod
import time
import logging
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

# Set up logging configuration
logging.basicConfig(
    filename='pump.log',
    filemode='a',
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO
)
logger = logging.getLogger()

class PumpControl:
    def __init__(self, port='COM13', baudrate=9600, address=1):
        """Initialize the PumpControl class with serial settings and Modbus address."""
        self.port = port
        self.baudrate = baudrate
        self.address = address  # Modbus slave address
        self.ser = None
        self.crc16 = crcmod.predefined.mkCrcFun('modbus')
        logger.info("PumpControl initialized with port %s, baudrate %d, address %d", port, baudrate, address)

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
        logger.info("Opened connection on port %s", self.port)

    def close_connection(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info("Closed connection on port %s", self.port)

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
            logger.warning("[Pump] Incomplete response received.")
            return None

        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self.calculate_crc(response[:-2])
        if received_crc != calculated_crc:
            logger.error("[Pump] CRC error: received %04X, expected %04X", received_crc, calculated_crc)
            return None

        # Extract registers from response
        data = response[3:-2]
        registers = struct.unpack('>' + 'H' * num_registers, data)
        logger.info("Read registers from %d: %s", start_address, registers)
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
            logger.warning("[Pump] Incomplete response received.")
            return False

        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self.calculate_crc(response[:-2])
        if received_crc != calculated_crc:
            logger.error("[Pump] CRC error: received %04X, expected %04X", received_crc, calculated_crc)
            return False

        logger.info("Pump status written successfully with status code %04X", status)
        return True

    def start_pump(self):
        """Start the pump by writing the start status to the control register."""
        if self.write_pump_status(0x0500):
            logger.info("Pump started successfully.")
        else:
            logger.error("Failed to start the pump.")

    def stop_pump(self):
        """Stop the pump by writing the stop status to the control register."""
        if self.write_pump_status(0x0000):
            logger.info("Pump stopped successfully.")
        else:
            logger.error("Failed to stop the pump.")

    def pause_pump(self):
        """Pause the pump by writing the pause status to the control register."""
        if self.write_pump_status(0x0600):
            logger.info("Pump paused successfully.")
        else:
            logger.error("Failed to pause the pump.")

    def read_pump_parameters(self):
        """Read the pump's pressure, flow rate, and stroke in one go."""
        parameters = self.read_registers(50, 6)  # Read 6 registers (2 for each float value)
        if parameters:
            flow = struct.unpack('>f', struct.pack('>HH', parameters[0], parameters[1]))[0]
            pressure = struct.unpack('>f', struct.pack('>HH', parameters[2], parameters[3]))[0]
            stroke = struct.unpack('>f', struct.pack('>HH', parameters[4], parameters[5]))[0]
            logger.info("Pump parameters - Flow: %.2f, Pressure: %.2f, Stroke: %.2f", flow, pressure, stroke)
            return flow, pressure, stroke
        else:
            logger.warning("Failed to read pump parameters.")
        return None, None, None

    def read_pump_status(self):
        """Read the current run state of the pump (start, pause, stop)."""
        request2 = struct.pack('>B B H H', self.address, 0x03, 5, 1)
        crc2 = self.calculate_crc(request2)
        request2 += struct.pack('<H', crc2)
        self.ser.reset_input_buffer()
        self.ser.write(request2)

        response_length2 = 1 + 1 + 1 + 2 + 2
        response2 = self.ser.read(response_length2)

        if len(response2) < response_length2:
            logger.warning("[Pump] Incomplete response received for status check.")
            return None

        received_crc2 = struct.unpack('<H', response2[-2:])[0]
        calculated_crc2 = self.calculate_crc(response2[:-2])
        if received_crc2 != calculated_crc2:
            logger.error("[Pump] CRC error in status read: received %04X, expected %04X", received_crc2, calculated_crc2)
            return None

        status_byte = response2[3]
        if status_byte == 0x05:
            logger.info("Pump status read as 'start'.")
            return "start"
        elif status_byte == 0x06:
            logger.info("Pump status read as 'pause'.")
            return "pause"
        elif status_byte == 0x00:
            logger.info("Pump status read as 'stop'.")
            return "stop"
        else:
            logger.warning("Unknown pump status byte: %02X", status_byte)
            return None

    def set_stroke(self, stroke_value):
        """Set the stroke of the pump (range 0-100%)."""
        if not 0 <= stroke_value <= 100:
            logger.warning("Invalid stroke value: %s. Must be between 0 and 100.", stroke_value)
            return False

        stroke_registers = struct.unpack('>HH', struct.pack('>f', stroke_value))
        result = self.write_registers(54, stroke_registers)
        if result:
            logger.info("Pump stroke set to %.2f%% successfully.", stroke_value)
        else:
            logger.error("Failed to set pump stroke to %.2f%%.", stroke_value)
        return result

    def write_registers(self, start_address, values):
        """Write multiple Modbus holding registers."""
        function_code = 0x10
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
            logger.warning("Incomplete response received during register write.")
            return False

        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self.calculate_crc(response[:-2])
        if received_crc != calculated_crc:
            logger.error("CRC error in write registers: received %04X, expected %04X", received_crc, calculated_crc)
            return False

        logger.info("Registers written successfully at address %d with values %s.", start_address, values)
        return True

    def read_pressure(self):
        """Read the real-time pressure."""
        registers = self.read_registers(52, 2)
        if registers:
            pressure = struct.unpack('>f', struct.pack('>HH', *registers))[0]
            logger.info("Read pressure: %.2f", pressure)
            return pressure
        else:
            logger.warning("Failed to read pressure.")
        return None

    def read_flow(self):
        """Read the instantaneous flow."""
        registers = self.read_registers(50, 2)
        if registers:
            flow = struct.unpack('>f', struct.pack('>HH', *registers))[0]
            logger.info("Read flow: %.2f", flow)
            return flow
        else:
            logger.warning("Failed to read flow.")
        return None

    def read_stroke(self):
        """Read the current stroke (itinerary) of the pump."""
        stroke_registers = self.read_registers(54, 2)
        if stroke_registers:
            stroke_value = struct.unpack('>f', struct.pack('>HH', *stroke_registers))[0]
            logger.info("Read stroke: %.2f", stroke_value)
            return stroke_value
        else:
            logger.warning("Failed to read stroke.")
        return None

class PumpControlThread(QThread):
    pressure_updated = Signal(float)  # Signal to update pressure in the GUI
    flow_updated = Signal(float, float)      # Signal to update flow in the GUI
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
                    cur_time = time.time()
                    if pressure is not None:
                        self.pressure_updated.emit(pressure)
                    if flow is not None:
                        self.flow_updated.emit(flow, cur_time)
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

