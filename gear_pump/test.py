import serial
import struct

class ModbusError(Exception):
    """Base class for Modbus exceptions."""
    pass

class CRCMismatchError(ModbusError):
    """Raised when CRC does not match."""
    pass

class ModbusExceptionError(ModbusError):
    """Raised when Modbus device returns an exception code."""
    pass

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

    def __enter__(self):
        """Enables usage of the class as a context manager."""
        self._open_serial()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensures the serial port is closed when exiting the context."""
        self._close_serial()

    def _open_serial(self):
        """Opens the serial port."""
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
                print(f"Opened serial port: {self.port}")
            except serial.SerialException as e:
                print(f"Failed to open serial port {self.port}: {e}")
                raise

    def _close_serial(self):
        """Closes the serial port."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"Closed serial port: {self.port}")

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
    #      READ OPERATIONS (Function Code 0x03)
    # ------------------------------------------------------
    def _construct_read_request(self, register_address, register_count=1):
        """
        Constructs the Modbus RTU request frame for reading registers (Function code 0x03).
        
        :param register_address: Starting address of the register to read
        :param register_count: Number of registers to read
        :return: Byte string of the request frame
        """
        request = struct.pack('>BBHH', self.slave_id, 0x03, register_address, register_count)
        crc = self._calculate_crc(request)
        request += struct.pack('<H', crc)
        return request

    def _parse_read_response(self, response, register_count=1):
        """
        Parses and validates the Modbus RTU response for a read operation (Function code 0x03).
        
        :param response: Bytes received from the device
        :param register_count: Number of registers expected
        :return: Parsed unsigned integer data
        :raises ModbusError: If response is invalid or CRC does not match
        """
        expected_length = 5 + 2 * register_count  # Slave ID + Func Code + Byte Count + Data + CRC
        if len(response) < expected_length:
            raise ModbusError(f"Incomplete response received. Expected {expected_length} bytes, got {len(response)} bytes.")
        
        # Unpack header
        slave_id, function_code, byte_count = struct.unpack('>BBB', response[:3])
        
        # Check for exception response (function_code with MSB set)
        if function_code == (0x03 | 0x80):
            exception_code = response[3]
            raise ModbusExceptionError(f"Modbus exception code: {exception_code}")
        
        if byte_count != 2 * register_count:
            raise ModbusError(f"Unexpected byte count: {byte_count}. Expected: {2 * register_count}")
        
        # Extract data
        data = response[3:3 + byte_count]
        unsigned_data = struct.unpack('>' + 'H' * register_count, data)
        
        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self._calculate_crc(response[:-2])
        
        if calculated_crc != received_crc:
            raise CRCMismatchError("CRC mismatch")
        
        return unsigned_data if register_count > 1 else unsigned_data[0]

    def read_register(self, register_address, register_count=1):
        """
        Reads registers from the Modbus device (Function code 0x03).
        
        :param register_address: Starting address of the register to read
        :param register_count: Number of registers to read
        :return: Parsed data from the registers
        :raises ModbusError: If any error occurs during communication
        """
        request = self._construct_read_request(register_address, register_count)
        self.ser.write(request)
        expected_length = 5 + 2 * register_count
        response = self.ser.read(expected_length)
        return self._parse_read_response(response, register_count)

    # ------------------------------------------------------
    #      SINGLE-REGISTER WRITE OPERATIONS (0x06)
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
        return request

    def _parse_write_response(self, response):
        """
        Parses and validates the Modbus RTU response for a single-register write (Function code 0x06).
        
        :param response: Bytes received from the device
        :return: (register_address, value) if successful
        :raises ModbusError: If response is invalid or CRC does not match
        """
        expected_length = 8  # Slave ID + Func Code + Register Address + Value + CRC
        if len(response) < expected_length:
            raise ModbusError(f"Incomplete response received. Expected {expected_length} bytes, got {len(response)} bytes.")
        
        # Unpack header
        slave_id, function_code = struct.unpack('>BB', response[:2])

        # Check for exception response
        if function_code == (0x06 | 0x80):
            exception_code = response[2]
            raise ModbusExceptionError(f"Modbus exception code: {exception_code}")

        # Extract register address and value
        register_address, written_value = struct.unpack('>HH', response[2:6])
        
        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self._calculate_crc(response[:-2])
        
        if calculated_crc != received_crc:
            raise CRCMismatchError("CRC mismatch")
        
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
        self.ser.write(request)
        response = self.ser.read(8)
        return self._parse_write_response(response)

    # ------------------------------------------------------
    #   MULTIPLE-REGISTER WRITE OPERATIONS (0x10)
    # ------------------------------------------------------
    def _construct_write_multiple_request(self, start_address, values):
        """
        Constructs the Modbus RTU request frame for writing multiple registers (Function code 0x10).
        
        :param start_address: Starting address of the registers to write
        :param values: List of 16-bit register values
        :return: Byte string of the request frame
        """
        register_count = len(values)
        byte_count = register_count * 2  # Each register is 2 bytes

        # Slave ID, Function code (0x10), Starting address, Quantity of registers, Byte count
        request = struct.pack('>BBHHB', self.slave_id, 0x10, start_address, register_count, byte_count)
        
        # Append the register values
        for val in values:
            request += struct.pack('>H', val)
        
        crc = self._calculate_crc(request)
        request += struct.pack('<H', crc)
        return request

    def _parse_write_multiple_response(self, response):
        """
        Parses and validates the Modbus RTU response for a multiple-register write (Function code 0x10).
        
        :param response: Bytes received from the device
        :return: (start_address, register_count) if successful
        :raises ModbusError: If response is invalid or CRC does not match
        """
        expected_length = 8  # Slave ID + Func Code + Start Address + Register Count + CRC
        if len(response) < expected_length:
            raise ModbusError(f"Incomplete response received. Expected {expected_length} bytes, got {len(response)} bytes.")
        
        # Unpack header
        slave_id, function_code = struct.unpack('>BB', response[:2])

        # Check for exception response
        if function_code == (0x10 | 0x80):
            exception_code = response[2]
            raise ModbusExceptionError(f"Modbus exception code: {exception_code}")

        # Extract start address and written register count
        start_address, register_count = struct.unpack('>HH', response[2:6])
        
        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = self._calculate_crc(response[:-2])
        
        if calculated_crc != received_crc:
            raise CRCMismatchError("CRC mismatch")
        
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
        self.ser.write(request)
        # Response for a multiple-register write is always 8 bytes
        response = self.ser.read(8)
        return self._parse_write_multiple_response(response)

    # ------------------------------------------------------
    #          READ METHODS (Flow, Rotate, Pressure, Temp)
    # ------------------------------------------------------
    def read_current_flow(self):
        """
        Reads the current flow rate from the gear pump.
        
        :return: Flow rate as integer (mL/min) or None if an error occurs
        """
        REGISTER_ADDRESS_FLOW = 0x04BE  # 1214
        try:
            flow = self.read_register(REGISTER_ADDRESS_FLOW)
            return flow
        except ModbusError as e:
            print(f"Error reading current flow rate: {e}")
            return None

    def read_rotate_rate(self):
        """
        Reads the current rotate rate from the gear pump.
        
        :return: Rotate rate as integer (R/min) or None if an error occurs
        """
        REGISTER_ADDRESS_ROTATE = 0x04C0  # 1216
        try:
            rotate = self.read_register(REGISTER_ADDRESS_ROTATE)
            return rotate
        except ModbusError as e:
            print(f"Error reading rotate rate: {e}")
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
            return pressure
        except ModbusError as e:
            print(f"Error reading pressure: {e}")
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
            return temperature
        except ModbusError as e:
            print(f"Error reading temperature: {e}")
            return None

    # ------------------------------------------------------
    #            WRITE METHODS (Flow, Rotate, Pump State)
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
            print("Error: flow_rate must be between 0 and 65535.")
            return False

        try:
            reg_addr, reg_val = self.write_register(REGISTER_ADDRESS_FLOW_WRITE, flow_rate)
            if reg_addr == REGISTER_ADDRESS_FLOW_WRITE and reg_val == flow_rate:
                return True
            else:
                print("Unexpected response from the device.")
                return False
        except ModbusError as e:
            print(f"Error setting flow rate: {e}")
            return False

    def set_rotate_rate(self, rotate_rate):
        """
        Sets the rotate rate of the gear pump using Modbus function code 0x06 (Write Single Register).
        
        :param rotate_rate: Desired rotate rate (0 to 65535)
        :return: True if successful, False otherwise
        """
        REGISTER_ADDRESS_ROTATE_WRITE = 0x04B2  # 1202

        if not (0 <= rotate_rate <= 0xFFFF):
            print("Error: rotate_rate must be between 0 and 65535.")
            return False

        try:
            reg_addr, reg_val = self.write_register(REGISTER_ADDRESS_ROTATE_WRITE, rotate_rate)
            if reg_addr == REGISTER_ADDRESS_ROTATE_WRITE and reg_val == rotate_rate:
                return True
            else:
                print("Unexpected response from the device.")
                return False
        except ModbusError as e:
            print(f"Error setting rotate rate: {e}")
            return False

    def set_pump_state(self, state):
        """
        Sets the pump state to ON or OFF by writing to three registers:
        1100, 1101, and 1102 using Modbus Function Code 16 (0x10).

        :param state: 1 to turn ON, 0 to turn OFF
        :return: True if successful, False otherwise
        """
        if state not in [0, 1]:
            print("Error: state must be 0 (OFF) or 1 (ON).")
            return False

        # Define start address and register values
        start_address = 1100
        register_count = 3

        # If state = 1, then registers = [1, 0, 0] => Pump ON
        # If state = 0, then registers = [0, 0, 1] => Pump OFF
        if state == 1:
            values = [1, 0, 0]
        else:
            values = [0, 0, 1]

        try:
            written_address, written_count = self.write_registers(start_address, values)
            # If the device echoes the correct address and number of registers, it's a success
            if written_address == start_address and written_count == register_count:
                return True
            else:
                print("Unexpected response from the device.")
                return False
        except ModbusError as e:
            print(f"Error setting pump state: {e}")
            return False

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

        # Set Flow Rate
        try:
            desired_flow = int(input("Enter the flow rate to set (in mL/min, e.g., 50, 100, etc.): "))
            # Multiply user input if the device expects scaled values
            if pump_controller.set_flow_rate(desired_flow * 10):
                print(f"Flow rate set to {desired_flow} mL/min successfully.")
            else:
                print("Failed to set flow rate.")
        except ValueError:
            print("Invalid input for flow rate.")

        # Set Rotate Rate
        try:
            desired_rate = int(input("Enter the rotate rate to set (0-65535): "))
            if pump_controller.set_rotate_rate(desired_rate):
                print(f"Rotate rate set to {desired_rate} R/min successfully.")
            else:
                print("Failed to set rotate rate.")
        except ValueError:
            print("Invalid input for rotate rate.")

        # Set Pump State
        try:
            pump_state = int(input("Enter pump state (1 for ON, 0 for OFF): "))
            if pump_controller.set_pump_state(pump_state):
                print(f"Pump state set to {'ON' if pump_state == 1 else 'OFF'} successfully.")
            else:
                print("Failed to set pump state.")
        except ValueError:
            print("Invalid input for pump state (must be 0 or 1).")
