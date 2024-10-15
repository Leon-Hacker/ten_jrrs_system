import serial
import struct
import crcmod

# Initialize the serial connection
ser = serial.Serial(
    port='/dev/tty.usbserial-AB0PEOBW',  # Replace with your serial port
    baudrate=9600,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=2  # Timeout in seconds
)

# Function to calculate CRC16 for Modbus RTU
crc16 = crcmod.predefined.mkCrcFun('modbus')

def read_register(slave_id, address):
    """
    Reads the value of a Modbus holding register.
    
    :param slave_id: Modbus slave ID
    :param address: Address of the register to read (0-based)
    :return: The value of the register or None if an error occurred
    """
    function_code = 0x03  # Function code for reading holding registers
    num_registers = 1     # We only need to read one register
    
    # Construct the request frame
    request = struct.pack('>B B H H', slave_id, function_code, address, num_registers)
    
    # Calculate CRC16
    crc = crc16(request)
    
    # Append CRC to the frame
    request += struct.pack('<H', crc)
    
    # Send the request frame
    ser.write(request)
    
    # Expected response length: 1 byte Slave ID + 1 byte Function Code + 1 byte Byte Count + 2 bytes Data + 2 bytes CRC
    response_length = 1 + 1 + 1 + 2 + 2
    response = ser.read(response_length)
    
    if len(response) < response_length:
        print("Incomplete response received.")
        return None
    
    # Validate CRC
    received_crc = struct.unpack('<H', response[-2:])[0]
    calculated_crc = crc16(response[:-2])
    
    if received_crc != calculated_crc:
        print(f"CRC error: received {received_crc:04X}, expected {calculated_crc:04X}")
        return None
    
    # Extract the register value from the response
    register_value = struct.unpack('>H', response[3:5])[0]
    
    return register_value

def write_register(slave_id, address, value):
    """
    Writes a value to a Modbus holding register.
    
    :param slave_id: Modbus slave ID
    :param address: Address of the register to write (0-based)
    :param value: Value to write to the register
    :return: True if successful, False otherwise
    """
    function_code = 0x06  # Function code for writing a single register
    
    # Construct the request frame
    request = struct.pack('>B B H H', slave_id, function_code, address, value)
    
    # Calculate CRC16
    crc = crc16(request)
    
    # Append CRC to the frame
    request += struct.pack('<H', crc)
    print(request.hex())
    # Send the request frame
    ser.write(request)
    
    # Expected response length: 8 bytes (echo of the request)
    response = ser.read(8)
    
    if len(response) < 8:
        print("Incomplete response received.")
        return False
    
    # Validate CRC
    received_crc = struct.unpack('<H', response[-2:])[0]
    calculated_crc = crc16(response[:-2])
    
    if received_crc != calculated_crc:
        print(f"CRC error: received {received_crc:04X}, expected {calculated_crc:04X}")
        return False
    
    return True

def set_time_control(slave_id, address, turn_on):
    """
    Turns the time control on or off.
    
    :param slave_id: Modbus slave ID
    :param address: Address of the time control register (0-based)
    :param turn_on: True to turn on, False to turn off
    :return: None
    """
    # Read the current register value
    current_value = read_register(slave_id, address)
    if current_value is None:
        print("Failed to read current register value.")
        return
    
    print(f"Current register value: {current_value:04X}")
    
    # Modify the second bit (bit 1) according to the desired state
    if turn_on:
        new_value = current_value | 0x0002  # Set the second bit to 1
    else:
        new_value = current_value & 0xFFFD  # Clear the second bit (set to 0)
    
    # Write the new value back to the register
    if write_register(slave_id, address, new_value):
        print(f"Successfully {'turned on' if turn_on else 'turned off'} time control.")
    else:
        print(f"Failed to {'turn on' if turn_on else 'turn off'} time control.")

# Address calculation for "时间控制" (Time Control)
# Documentation says 40007, so use 40007 - 1 = 6 (0-based)
time_control_address = 40007 - 40001

# Example: Turn ON the time control
set_time_control(1, time_control_address, turn_on=True)

# Example: Turn OFF the time control
# set_time_control(1, time_control_address, turn_on=False)

# Close the serial connection
ser.close()