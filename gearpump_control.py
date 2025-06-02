import time
import serial
import struct
import logging
from PySide6.QtCore import QObject, Signal, QMutex, QMutexLocker, QTimer
from logging.handlers import RotatingFileHandler

# ----------------------------
#   Logger Configuration
# ----------------------------

# Configure a logger for the gear pump controller with size-based rotation
gearpump_logger = logging.getLogger('GearPumpControl')
gearpump_handler = RotatingFileHandler(
    'logs/gearpump.log',
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=5,         # Keep up to 5 backup files
    encoding='utf-8'
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
gearpump_handler.setFormatter(formatter)
gearpump_logger.addHandler(gearpump_handler)
gearpump_logger.setLevel(logging.INFO)

# Optionally, add a console handler for real-time feedback
# console_handler = logging.StreamHandler()
# console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
# gearpump_logger.addHandler(console_handler)

# ----------------------------
#        Exception Classes
# ----------------------------

class ModbusError(Exception):
    """Base class for Modbus exceptions."""
    pass

class CRCMismatchError(ModbusError):
    """Raised when CRC does not match."""
    pass

class ModbusExceptionError(ModbusError):
    """Raised when Modbus device returns an exception code."""
    pass

# ----------------------------
#      GearPumpController
# ----------------------------

class GearPumpController:
    def __init__(self, port, baudrate=9600, timeout=1, slave_id=1):
        """
        Initializes the GearPumpController with serial port parameters and Modbus settings.
        
        :param port: Serial port (e.g., 'COM20' or '/dev/ttyUSB0')
        :param baudrate: Baud rate for serial communication
        :param timeout: Read timeout in seconds
        :param slave_id: Modbus slave ID
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.slave_id = slave_id
        self.ser = None
        gearpump_logger.info("GearPumpController initialized with port=%s, baudrate=%d, timeout=%d, slave_id=%d",
                             port, baudrate, timeout, slave_id)

    def __enter__(self):
        """Enables usage of the class as a context manager."""
        self.open_serial()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensures the serial port is closed when exiting the context."""
        self.close_serial()

    def open_serial(self):
        """Public method to open the serial port."""
        if self.ser is None or not self.ser.is_open:
            try:
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self.timeout
                )
                gearpump_logger.info("Opened serial port: %s", self.port)
            except serial.SerialException as e:
                gearpump_logger.error("Failed to open serial port %s: %s", self.port, str(e))
                raise

    def close_serial(self):
        """Public method to close the serial port."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            gearpump_logger.info("Closed serial port: %s", self.port)

    def _calculate_crc(self, data):
        """
        Calculates the Modbus CRC16 checksum.
        
        :param data: Bytes for which CRC is to be calculated
        :return: CRC16 as integer
        """
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return crc

    # ------------------------------------------------------
    #         READ COILS (Function Code 0x01)
    # ------------------------------------------------------
    def _construct_read_coils_request(self, coil_address, coil_count=1):
        """
        Constructs the Modbus RTU request frame for reading coils (Function code 0x01).
        
        :param coil_address: Starting address of the coil(s) to read
        :param coil_count: Number of coils to read
        :return: Byte string of the request frame
        """
        # Slave ID, Function code (0x01), Starting address, Coil count
        request = struct.pack('>BBHH', self.slave_id, 0x01, coil_address, coil_count)
        
        # Calculate and append CRC
        crc = self._calculate_crc(request)
        request += struct.pack('<H', crc)
        gearpump_logger.debug("Constructed Read Coils Request: %s", request.hex())
        return request

    def _parse_coils_response(self, response, coil_count=1):
        """
        Parses and validates the Modbus RTU response for a read-coils operation (Function code 0x01).
        
        :param response: Bytes received from the device
        :param coil_count: Number of coils expected
        :return: A list of coil states (0 or 1) of length coil_count
        :raises ModbusError: If response is invalid or CRC does not match
        """
        # Expected response length:
        # Slave ID (1 byte) + Function Code (1 byte) + Byte Count (1 byte) + Coil Data + CRC (2 bytes)
        # Coil Data = ceil(coil_count / 8) bytes
        byte_count_expected = (coil_count + 7) // 8  # Each byte holds up to 8 coils
        expected_length = 3 + byte_count_expected + 2  # 3 (header) + data + 2 (CRC)

        if len(response) < expected_length:
            gearpump_logger.error("Incomplete response received. Expected %d bytes, got %d bytes.", expected_length, len(response))
            raise ModbusError(f"Incomplete response received. Expected {expected_length} bytes, got {len(response)} bytes.")

        # Unpack header
        slave_id, function_code, byte_count = struct.unpack('>BBB', response[:3])
        gearpump_logger.debug("Parsed Response Header - Slave ID: %d, Function Code: %d, Byte Count: %d", slave_id, function_code, byte_count)
        
        # Check for exception response
        if function_code == (0x01 | 0x80):
            exception_code = response[2]
            gearpump_logger.error("Modbus exception code received: %d", exception_code)
            raise ModbusExceptionError(f"Modbus exception code: {exception_code}")

        if byte_count != byte_count_expected:
            gearpump_logger.error("Unexpected byte count: %d. Expected: %d", byte_count, byte_count_expected)
            raise ModbusError(f"Unexpected byte count: {byte_count}. Expected: {2 * coil_count}")

        coil_data = response[3:3 + byte_count]
        gearpump_logger.debug("Coil Data: %s", coil_data.hex())
        
        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self._calculate_crc(response[:-2])
        if calculated_crc != received_crc:
            gearpump_logger.error("CRC mismatch. Calculated: 0x%04X, Received: 0x%04X", calculated_crc, received_crc)
            raise CRCMismatchError("CRC mismatch")
        gearpump_logger.debug("CRC validation passed.")

        # Parse the coil data bits
        coils = []
        for i in range(coil_count):
            byte_index = i // 8
            bit_index = i % 8
            coil_state = (coil_data[byte_index] >> bit_index) & 0x01
            coils.append(coil_state)

        gearpump_logger.info("Read Coils Response: %s", coils)
        return coils

    def read_coils(self, coil_address, coil_count=1):
        """
        Reads coils from the Modbus device (Function code 0x01).
        
        :param coil_address: Starting address of the coil(s) to read
        :param coil_count: Number of coils to read
        :return: A list of coil states (0 or 1) of length coil_count
        :raises ModbusError: If any error occurs during communication
        """
        request = self._construct_read_coils_request(coil_address, coil_count)
        self.ser.reset_input_buffer()
        self.ser.write(request)
        gearpump_logger.info("Sent Read Coils Request: %s", request.hex())

        byte_count_expected = (coil_count + 7) // 8
        expected_length = 3 + byte_count_expected + 2
        response = self.ser.read(expected_length)
        gearpump_logger.info("Received Read Coils Response: %s", response.hex())
        return self._parse_coils_response(response, coil_count)

    # ------------------------------------------------------
    #         READ HOLDING REGISTERS (Function Code 0x03)
    # ------------------------------------------------------
    def _construct_read_request(self, register_address, register_count=1):
        """
        Constructs the Modbus RTU request frame for reading holding registers (Function code 0x03).
        
        :param register_address: Starting address of the register to read
        :param register_count: Number of registers to read
        :return: Byte string of the request frame
        """
        request = struct.pack('>BBHH', self.slave_id, 0x03, register_address, register_count)
        crc = self._calculate_crc(request)
        request += struct.pack('<H', crc)
        gearpump_logger.debug("Constructed Read Registers Request: %s", request.hex())
        return request

    def _parse_read_response(self, response, register_count=1):
        """
        Parses and validates the Modbus RTU response for a read operation (Function code 0x03).
        
        :param response: Bytes received from the device
        :param register_count: Number of registers expected
        :return: Parsed unsigned integer data
        :raises ModbusError: If response is invalid or CRC does not match
        """
        expected_length = 5 + 2 * register_count
        if len(response) < expected_length:
            gearpump_logger.error("Incomplete response received. Expected %d bytes, got %d bytes.", expected_length, len(response))
            raise ModbusError(f"Incomplete response received. Expected {expected_length} bytes, got {len(response)} bytes.")
        
        # Unpack header
        slave_id, function_code, byte_count = struct.unpack('>BBB', response[:3])
        gearpump_logger.debug("Parsed Response Header - Slave ID: %d, Function Code: %d, Byte Count: %d", slave_id, function_code, byte_count)
        
        if function_code == (0x03 | 0x80):
            exception_code = response[2]
            gearpump_logger.error("Modbus exception code received: %d", exception_code)
            raise ModbusExceptionError(f"Modbus exception code: {exception_code}")

        if byte_count != 2 * register_count:
            gearpump_logger.error("Unexpected byte count: %d. Expected: %d", byte_count, 2 * register_count)
            raise ModbusError(f"Unexpected byte count: {byte_count}. Expected: {2 * register_count}")

        data = response[3:3 + byte_count]
        unsigned_data = struct.unpack('>' + 'H' * register_count, data)
        gearpump_logger.debug("Register Data: %s", unsigned_data)

        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self._calculate_crc(response[:-2])
        if calculated_crc != received_crc:
            gearpump_logger.error("CRC mismatch. Calculated: 0x%04X, Received: 0x%04X", calculated_crc, received_crc)
            raise CRCMismatchError("CRC mismatch")
        gearpump_logger.debug("CRC validation passed.")

        gearpump_logger.info("Read Registers Response: %s", unsigned_data)
        return unsigned_data if register_count > 1 else unsigned_data[0]

    def read_register(self, register_address, register_count=1):
        """
        Reads holding registers from the Modbus device (Function code 0x03).
        
        :param register_address: Starting address of the register to read
        :param register_count: Number of registers to read
        :return: Parsed data from the registers
        :raises ModbusError: If any error occurs during communication
        """
        request = self._construct_read_request(register_address, register_count)
        self.ser.reset_input_buffer()
        self.ser.write(request)
        gearpump_logger.info("Sent Read Registers Request: %s", request.hex())
        response = self.ser.read(5 + 2 * register_count)
        gearpump_logger.info("Received Read Registers Response: %s", response.hex())
        return self._parse_read_response(response, register_count)

    # ------------------------------------------------------
    #   SINGLE-REGISTER WRITE (Function Code 0x06)
    # ------------------------------------------------------
    def _construct_write_request(self, register_address, value):
        """
        Constructs the Modbus RTU request frame for writing a single register (Function code 0x06).
        
        :param register_address: Address of the register to write
        :param value: 16-bit unsigned value to write
        :return: Byte string of the request frame
        """
        request = struct.pack('>BBHH', self.slave_id, 0x06, register_address, value)
        crc = self._calculate_crc(request)
        request += struct.pack('<H', crc)
        gearpump_logger.debug("Constructed Write Register Request: %s", request.hex())
        return request

    def _parse_write_response(self, response):
        """
        Parses and validates the Modbus RTU response for a single-register write (Function code 0x06).
        
        :param response: Bytes received from the device
        :return: (register_address, value) if successful
        :raises ModbusError: If response is invalid or CRC does not match
        """
        expected_length = 8
        if len(response) < expected_length:
            gearpump_logger.error("Incomplete response received. Expected %d bytes, got %d bytes.", expected_length, len(response))
            raise ModbusError(f"Incomplete response received. Expected {expected_length} bytes, got {len(response)} bytes.")
        
        slave_id, function_code = struct.unpack('>BB', response[:2])
        gearpump_logger.debug("Parsed Response Header - Slave ID: %d, Function Code: %d", slave_id, function_code)
        
        if function_code == (0x06 | 0x80):
            exception_code = response[2]
            gearpump_logger.error("Modbus exception code received: %d", exception_code)
            raise ModbusExceptionError(f"Modbus exception code: {exception_code}")

        register_address, written_value = struct.unpack('>HH', response[2:6])
        gearpump_logger.debug("Write Register Data - Address: %d, Value: %d", register_address, written_value)

        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self._calculate_crc(response[:-2])
        if calculated_crc != received_crc:
            gearpump_logger.error("CRC mismatch. Calculated: 0x%04X, Received: 0x%04X", calculated_crc, received_crc)
            raise CRCMismatchError("CRC mismatch")
        gearpump_logger.debug("CRC validation passed.")

        gearpump_logger.info("Write Register Response - Address: %d, Value: %d", register_address, written_value)
        return register_address, written_value

    def write_register(self, register_address, value):
        """
        Writes a single 16-bit value to the Modbus device (Function code 0x06).
        
        :param register_address: Address of the register to write
        :param value: 16-bit unsigned value
        :return: (register_address, written_value) if successful
        :raises ModbusError: If any error occurs during communication
        """
        request = self._construct_write_request(register_address, value)
        self.ser.reset_input_buffer()
        self.ser.write(request)
        gearpump_logger.info("Sent Write Register Request: %s", request.hex())
        response = self.ser.read(8)
        gearpump_logger.info("Received Write Register Response: %s", response.hex())
        return self._parse_write_response(response)

    # ------------------------------------------------------
    #  MULTIPLE-REGISTER WRITE (Function Code 0x10)
    # ------------------------------------------------------
    def _construct_write_multiple_request(self, start_address, values):
        """
        Constructs the Modbus RTU request frame for writing multiple registers (Function code 0x10).
        
        :param start_address: Starting address of the registers to write
        :param values: List of 16-bit register values
        :return: Byte string of the request frame
        """
        register_count = len(values)
        byte_count = register_count * 2

        # Slave ID, Function code (0x10), Start Address, Register Count, Byte Count
        request = struct.pack('>BBHHB', self.slave_id, 0x10, start_address, register_count, byte_count)
        
        for val in values:
            request += struct.pack('>H', val)
        
        crc = self._calculate_crc(request)
        request += struct.pack('<H', crc)
        gearpump_logger.debug("Constructed Write Multiple Registers Request: %s", request.hex())
        return request

    def _parse_write_multiple_response(self, response):
        """
        Parses and validates the Modbus RTU response for a multiple-register write (Function code 0x10).
        
        :param response: Bytes received from the device
        :return: (start_address, register_count) if successful
        :raises ModbusError: If response is invalid or CRC does not match
        """
        expected_length = 8
        if len(response) < expected_length:
            gearpump_logger.error("Incomplete response received. Expected %d bytes, got %d bytes.", expected_length, len(response))
            raise ModbusError(f"Incomplete response received. Expected {expected_length} bytes, got {len(response)} bytes.")

        slave_id, function_code = struct.unpack('>BB', response[:2])
        gearpump_logger.debug("Parsed Response Header - Slave ID: %d, Function Code: %d", slave_id, function_code)
        
        if function_code == (0x10 | 0x80):
            exception_code = response[2]
            gearpump_logger.error("Modbus exception code received: %d", exception_code)
            raise ModbusExceptionError(f"Modbus exception code: {exception_code}")

        start_address, register_count = struct.unpack('>HH', response[2:6])
        gearpump_logger.debug("Write Multiple Registers Data - Start Address: %d, Register Count: %d", start_address, register_count)

        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self._calculate_crc(response[:-2])
        if calculated_crc != received_crc:
            gearpump_logger.error("CRC mismatch. Calculated: 0x%04X, Received: 0x%04X", calculated_crc, received_crc)
            raise CRCMismatchError("CRC mismatch")
        gearpump_logger.debug("CRC validation passed.")

        gearpump_logger.info("Write Multiple Registers Response - Start Address: %d, Register Count: %d", start_address, register_count)
        return start_address, register_count

    def write_registers(self, start_address, values):
        """
        Writes multiple registers to the Modbus device (Function code 0x10).
        
        :param start_address: Starting address of the registers to write
        :param values: List of 16-bit unsigned values
        :return: (start_address, register_count) if successful
        :raises ModbusError: If any error occurs during communication
        """
        request = self._construct_write_multiple_request(start_address, values)
        self.ser.reset_input_buffer()
        self.ser.write(request)
        gearpump_logger.info("Sent Write Multiple Registers Request: %s", request.hex())
        response = self.ser.read(8)
        gearpump_logger.info("Received Write Multiple Registers Response: %s", response.hex())
        return self._parse_write_multiple_response(response)

    # ------------------------------------------------------
    #       READ METHODS (Flow, Rotate, Pressure, Temp)
    # ------------------------------------------------------
    def read_current_flow(self):
        """
        Reads the current flow rate from the gear pump.
        
        :return: Flow rate as integer (mL/min) or None if an error occurs
        """
        REGISTER_ADDRESS_FLOW = 0x04BE  # 1214
        try:
            flow = self.read_register(REGISTER_ADDRESS_FLOW)
            gearpump_logger.info("Current Flow Rate: %d mL/min", flow)
            return flow
        except ModbusError as e:
            gearpump_logger.error("Error reading current flow rate: %s", e)
            return None

    def read_rotate_rate(self):
        """
        Reads the current rotate rate from the gear pump.
        
        :return: Rotate rate as integer (R/min) or None if an error occurs
        """
        REGISTER_ADDRESS_ROTATE = 0x04C0  # 1216
        try:
            rotate = self.read_register(REGISTER_ADDRESS_ROTATE)
            gearpump_logger.info("Current Rotate Rate: %d R/min", rotate)
            return rotate
        except ModbusError as e:
            gearpump_logger.error("Error reading rotate rate: %s", e)
            return None

    def read_pressure(self):
        """
        Reads the current pressure from the gear pump.
        
        :return: Pressure as float (bar) or None if an error occurs
        """
        REGISTER_ADDRESS_PRESSURE = 0x0BBE  # 3006
        try:
            pressure_raw = self.read_register(REGISTER_ADDRESS_PRESSURE)
            pressure = pressure_raw / 100  # Assuming the pressure is scaled by 100
            gearpump_logger.info("Current Pressure: %.2f bar", pressure)
            return pressure
        except ModbusError as e:
            gearpump_logger.error("Error reading pressure: %s", e)
            return None

    def read_temperature(self):
        """
        Reads the temperature of the fluid in the gear pump.
        
        :return: Temperature as float (°C) or None if an error occurs
        """
        REGISTER_ADDRESS_TEMPERATURE = 3010  # Decimal address as per user code
        try:
            temperature_raw = self.read_register(REGISTER_ADDRESS_TEMPERATURE)
            temperature = temperature_raw / 10  # Assuming the temperature is scaled by 10
            gearpump_logger.info("Current Temperature: %.2f °C", temperature)
            return temperature
        except ModbusError as e:
            gearpump_logger.error("Error reading temperature: %s", e)
            return None

    # ------------------------------------------------------
    #       WRITE METHODS (Flow, Rotate, Pump State)
    # ------------------------------------------------------
    def set_flow_rate(self, flow_rate):
        """
        Sets the flow rate of the gear pump using Modbus function code 0x06 (Write Single Register).
        
        :param flow_rate: Desired flow rate (0 to 65535)
                          (Device might interpret it differently, e.g., dividing by 10 for mL/min)
        :return: True if successful, False otherwise
        """
        REGISTER_ADDRESS_FLOW_WRITE = 0x04B0  # 1200

        if not (0 <= flow_rate <= 0xFFFF):
            gearpump_logger.error("Flow rate must be between 0 and 65535. Provided: %d", flow_rate)
            return False

        try:
            reg_addr, reg_val = self.write_register(REGISTER_ADDRESS_FLOW_WRITE, flow_rate)
            if reg_addr == REGISTER_ADDRESS_FLOW_WRITE and reg_val == flow_rate:
                gearpump_logger.info("Flow rate set to %d successfully.", flow_rate)
                return True
            else:
                gearpump_logger.warning("Unexpected response when setting flow rate. Address: %d, Value: %d", reg_addr, reg_val)
                return False
        except ModbusError as e:
            gearpump_logger.error("Error setting flow rate: %s", e)
            return False

    def set_rotate_rate(self, rotate_rate):
        """
        Sets the rotate rate of the gear pump using Modbus function code 0x06 (Write Single Register).
        
        :param rotate_rate: Desired rotate rate (0 to 65535)
        :return: True if successful, False otherwise
        """
        REGISTER_ADDRESS_ROTATE_WRITE = 0x04B2  # 1202

        if not (0 <= rotate_rate <= 0xFFFF):
            gearpump_logger.error("Rotate rate must be between 0 and 65535. Provided: %d", rotate_rate)
            return False

        try:
            reg_addr, reg_val = self.write_register(REGISTER_ADDRESS_ROTATE_WRITE, rotate_rate)
            if reg_addr == REGISTER_ADDRESS_ROTATE_WRITE and reg_val == rotate_rate:
                gearpump_logger.info("Rotate rate set to %d successfully.", rotate_rate)
                return True
            else:
                gearpump_logger.warning("Unexpected response when setting rotate rate. Address: %d, Value: %d", reg_addr, reg_val)
                return False
        except ModbusError as e:
            gearpump_logger.error("Error setting rotate rate: %s", e)
            return False

    def set_pump_state(self, state):
        """
        Sets the pump state to ON or OFF by writing to three registers:
        1100, 1101, and 1102 using Modbus Function Code 0x10.

        :param state: 1 to turn ON, 0 to turn OFF
        :return: True if successful, False otherwise
        """
        if state not in [0, 1]:
            gearpump_logger.error("Invalid pump state: %d. Must be 0 (OFF) or 1 (ON).", state)
            return False

        start_address = 1100
        register_count = 3

        if state == 1:
            values = [1, 0, 0]  # Pump ON
        else:
            values = [0, 0, 1]  # Pump OFF

        try:
            written_address, written_count = self.write_registers(start_address, values)
            if written_address == start_address and written_count == register_count:
                gearpump_logger.info("Pump state set to %s successfully.", "ON" if state == 1 else "OFF")
                return True
            else:
                gearpump_logger.warning("Unexpected response when setting pump state. Address: %d, Count: %d",
                                        written_address, written_count)
                return False
        except ModbusError as e:
            gearpump_logger.error("Error setting pump state: %s", e)
            return False

    # ------------------------------------------------------
    #    NEW METHOD: READ THE PUMP'S RUNNING STATE (COIL)
    # ------------------------------------------------------
    def read_pump_state(self):
        """
        Reads the running state of the pump (ON or OFF) by reading a single coil (Function Code 0x01).
        Coil Address: 0x0433 (1075)
        
        :return: 'ON' if coil = 0x01, 'OFF' if coil = 0x00, or None if an error occurs
        """
        COIL_ADDRESS_PUMP_STATE = 0x0433  # 1075

        try:
            coils = self.read_coils(COIL_ADDRESS_PUMP_STATE, coil_count=1)
            # coils is a list of 0/1 for each coil read
            if not coils:  # Empty list or error
                gearpump_logger.warning("No coil data returned for pump state.")
                return None

            coil_status = coils[0]
            state = "ON" if coil_status == 1 else "OFF"
            gearpump_logger.info("Pump State Read: %s", state)
            return state
        except ModbusError as e:
            gearpump_logger.error("Error reading pump state: %s", e)
            return None

from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker, QObject, QTimer

class GearpumpControlWorker(QObject):
    # ----------------------
    #        SIGNALS
    # ----------------------
    pump_state_updated = Signal(str)            # E.g., "ON" or "OFF"
    flow_rate_updated = Signal(int, float)             # mL/min (raw reading from read_current_flow)
    rotate_rate_updated = Signal(int)           # R/min (raw reading from read_rotate_rate)
    pressure_updated = Signal(float)            # bar (from read_pressure)
    temperature_updated = Signal(float, float, float)         # °C (from read_temperature)

    flow_rate_set = Signal(int)
    rotate_rate_set = Signal(int)
    start_pump_set = Signal(int)
    stop_pump_set = Signal(int)

    pump_started = Signal()                     # Signal to indicate pump worker has started
    pump_stopped = Signal()                     # Signal to indicate pump worker has stopped
    button_checked = Signal(int)
    check_rotate_rate_signal = Signal()

    interop = Signal()

    # Additional signals if you need to notify GUI about control commands
    flow_rate_set_response = Signal(bool)       # True if setting flow rate was successful
    rotate_rate_set_response = Signal(bool)     # True if setting rotate rate was successful
    pump_state_set_response = Signal(bool)      # True if setting pump state was successful

    def __init__(self, gearpump_control: GearPumpController):
        """
        Worker class to monitor and control gear pump states from a separate thread.
        
        :param gearpump_control: An instance of GearPumpController (already configured).
        """
        super().__init__()
        self.running = True
        self.mutex = QMutex()

        self.gearpump_control = gearpump_control  # We'll use this object to read/write states
        self.cur_rotate_rate = 0
        self.cur_pressure = 0
        self.cur_state = None

        self.poll_timer = None
        self.poll_interval = 900  # milliseconds (adjust as desired for your application)

    def start_monitoring(self):
        """
        Start a QTimer to periodically poll the gear pump states (flow, rotate rate, etc.)
        and emit signals to the GUI.
        """
        self.poll_timer = QTimer()
        self.poll_timer.setInterval(self.poll_interval)
        self.poll_timer.timeout.connect(self.monitor_gearpump_state)
        self.poll_timer.start()

        # Emit that we've started
        self.pump_started.emit()

    def monitor_gearpump_state(self):
        """
        Periodically called by QTimer to read the gear pump states and emit the corresponding signals.
        """
        if not self.running:
            # If someone requested us to stop, then stop the timer
            self.poll_timer.stop()
            return
        
        QThread.msleep(100)

        # Avoid concurrent reads/writes: lock the gear pump object
        with QMutexLocker(self.mutex):
            try:
                # 1. Read flow rate
                flow = self.gearpump_control.read_current_flow()
                cur_time = time.time()
                if flow is not None:
                    self.flow_rate_updated.emit(flow, cur_time)

                # 2. Read rotate rate
                rotate = self.gearpump_control.read_rotate_rate()
                if rotate is not None:
                    self.rotate_rate_updated.emit(rotate)
                    self.cur_rotate_rate = rotate

                # 3. Read pressure
                pressure = self.gearpump_control.read_pressure()
                if pressure is not None:
                    self.pressure_updated.emit(pressure)

                # 4. Read temperature
                temperature = self.gearpump_control.read_temperature()
                if temperature is not None:
                    self.temperature_updated.emit(temperature, pressure, cur_time)

                # 5. Read pump running state (coil)
                running_state = self.gearpump_control.read_pump_state()
                if running_state:
                    self.pump_state_updated.emit(running_state)
                    self.cur_state = running_state

            except Exception as e:
                print(f"[GearpumpControlWorker] Error monitoring gear pump state: {e}")

        QThread.msleep(100)

    def stop(self):
        """
        Stop the monitoring loop. The worker will gracefully end once the poll_timer stops.
        """
        self.running = False

    # ----------------------
    #    CONTROL COMMANDS
    # ----------------------
    def set_flow_rate(self, flow_rate: int):
        """
        Request to set the flow rate (mL/min). This method can be called from the GUI.
        
        :param flow_rate: Desired flow rate
        """
        with QMutexLocker(self.mutex):
            try:
                # For example, multiply the user input if your device expects scaled values
                success = self.gearpump_control.set_flow_rate(flow_rate * 10)
                self.flow_rate_set_response.emit(success)
            except Exception as e:
                print(f"[GearpumpControlWorker] Error setting flow rate: {e}")
                self.flow_rate_set_response.emit(False)

    def set_rotate_rate(self, rotate_rate: int):
        """
        Request to set the rotate rate (R/min).
        
        :param rotate_rate: Desired rotate rate
        """
        with QMutexLocker(self.mutex):
            try:
                success = self.gearpump_control.set_rotate_rate(rotate_rate)
                self.rotate_rate_set_response.emit(success)
            except Exception as e:
                print(f"[GearpumpControlWorker] Error setting rotate rate: {e}")
                self.rotate_rate_set_response.emit(False)

    def set_rotate_rate_checked(self,rotate_rate:int):
        with QMutexLocker(self.mutex):
            try:
                success = self.gearpump_control.set_rotate_rate(rotate_rate)
                self.rotate_rate_set_response.emit(success)
            except Exception as e:
                print(f"[GearpumpControlWorker] Error setting rotate rate: {e}")
                self.rotate_rate_set_response.emit(False)

        # Check the current rotate rate and resend command if necessary
        QTimer.singleShot(1200, lambda: self.check_rotate_rate(rotate_rate))

    def check_rotate_rate(self,rotate_rate:int):
        with QMutexLocker(self.mutex):
            if abs(self.cur_rotate_rate - rotate_rate) < 10:
                self.interop.emit()
                return
            else:
                print("Current rotate rate does not match the desired rate. Resending command.")
                try:
                    success = self.gearpump_control.set_rotate_rate(rotate_rate)
                    self.rotate_rate_set_response.emit(success)
                except Exception as e:
                    print(f"[GearpumpControlWorker] Error setting rotate rate: {e}")
                    self.rotate_rate_set_response.emit(False)

                QTimer.singleShot(1200, lambda: self.check_rotate_rate(rotate_rate))

    def set_pump_state(self, state: int):
        """
        Request to set pump state (ON = 1, OFF = 0).
        
        :param state: 1 for ON, 0 for OFF
        """
        with QMutexLocker(self.mutex):
            try:
                success = self.gearpump_control.set_pump_state(state)
                self.pump_state_set_response.emit(success)
            except Exception as e:
                print(f"[GearpumpControlWorker] Error setting pump state: {e}")
                self.pump_state_set_response.emit(False)
    
    def turnoff_pump_checked(self):
        with QMutexLocker(self.mutex):
            try:
                success = self.gearpump_control.set_pump_state(0)
                self.pump_state_set_response.emit(success)
            except Exception as e:
                print(f"[GearpumpControlWorker] Error setting pump state: {e}")
                self.pump_state_set_response.emit(False)

        # Check the current pump state and resend command if necessary
        QTimer.singleShot(1000, lambda: self.check_pump_close())

    def check_pump_close(self):
        with QMutexLocker(self.mutex):
            if self.cur_state == "OFF":
                return
            else:
                print("Current pump state does not match the desired state. Resending command.")
                try:
                    success = self.gearpump_control.set_pump_state(0)
                    self.pump_state_set_response.emit(success)
                except Exception as e:
                    print(f"[GearpumpControlWorker] Error setting pump state: {e}")
                    self.pump_state_set_response.emit(False)

                QTimer.singleShot(1000, lambda: self.check_pump_close())

# ----------------------------------------------------------
#                    EXAMPLE USAGE
# ----------------------------------------------------------
if __name__ == '__main__':
    port = 'COM20'  # Update with your correct COM port
    with GearPumpController(port=port) as pump_controller:
        # Read Current Flow
        flow = pump_controller.read_current_flow()
        if flow is not None:
            print(f"Current Flow: {flow} mL/min")

        # Read Rotate Rate
        rotate = pump_controller.read_rotate_rate()
        if rotate is not None:
            print(f"Rotate Rate: {rotate} R/min")

        # Read Pressure
        pressure = pump_controller.read_pressure()
        if pressure is not None:
            print(f"Pressure: {pressure} bar")

        # Read Temperature
        temp = pump_controller.read_temperature()
        if temp is not None:
            print(f"Temperature: {temp}°C")

        # Set Flow Rate (example)
        try:
            desired_flow = int(input("Enter the flow rate to set (in mL/min, e.g., 50, 100, etc.): "))
            if pump_controller.set_flow_rate(desired_flow * 10):  # Multiply if device expects scaling
                print(f"Flow rate set to {desired_flow} mL/min successfully.")
            else:
                print("Failed to set flow rate.")
        except ValueError:
            print("Invalid input for flow rate.")

        # Set Rotate Rate (example)
        try:
            desired_rate = int(input("Enter the rotate rate to set (0-65535): "))
            if pump_controller.set_rotate_rate(desired_rate):
                print(f"Rotate rate set to {desired_rate} R/min successfully.")
            else:
                print("Failed to set rotate rate.")
        except ValueError:
            print("Invalid input for rotate rate.")

        # Set Pump State (example)
        try:
            pump_state = int(input("Enter pump state (1 for ON, 0 for OFF): "))
            if pump_controller.set_pump_state(pump_state):
                print(f"Pump state set to {'ON' if pump_state == 1 else 'OFF'} successfully.")
            else:
                print("Failed to set pump state.")
        except ValueError:
            print("Invalid input for pump state (must be 0 or 1).")

        # **Read Pump Running State** (example usage)
        running_state = pump_controller.read_pump_state()
        if running_state is not None:
            print(f"Pump is currently: {running_state}")
        else:
            print("Failed to read pump running state.")
