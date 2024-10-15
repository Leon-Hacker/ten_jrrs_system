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

def write_single_register(slave_id, address, value):
    """
    Writes a single register on a Modbus slave device.
    
    :param slave_id: ID of the Modbus slave
    :param address: Register address (0-based)
    :param value: Value to write to the register (as a 16-bit value)
    :return: True if successful, False otherwise
    """
    function_code = 0x06  # Function code for writing a single holding register
    
    # Construct the request frame
    request = struct.pack('>B B H H', slave_id, function_code, address, value)
    
    # Calculate CRC16
    crc = crc16(request)
    
    # Append CRC to the frame
    request += struct.pack('<H', crc)
    
    # Send the request frame to the slave device
    ser.write(request)
    
    # Expected response length: 8 bytes (echo of the request)
    response = ser.read(8)
    
    if len(response) < 8:
        print("Incomplete response received.")
        return False
    
    # Validate CRC in response
    received_crc = struct.unpack('<H', response[-2:])[0]
    calculated_crc = crc16(response[:-2])
    
    if received_crc != calculated_crc:
        print(f"CRC error: received {received_crc:04X}, expected {calculated_crc:04X}")
        return False
    
    return True

# Address calculation for "恒流速度" (Constant Flow Speed)
# Documentation says 40073, so use 40073 - 1 = 72 (0-based)
address = 40073 - 40001

# Value to set (e.g., 75% speed)
value_to_set = 1  # This would be 75% if it's stored as a percentage

# Write the value to the register
if write_single_register(1, address, value_to_set):
    print(f"Successfully set 恒流速度 (Constant Flow Speed) to {value_to_set}%")
else:
    print("Failed to set 恒流速度 (Constant Flow Speed).")

# Close the serial connection
ser.close()