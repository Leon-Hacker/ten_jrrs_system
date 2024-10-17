import serial
import struct
import crcmod

# Initialize the serial connection
ser = serial.Serial(
    port='COM13',  # Replace with your serial port
    baudrate=9600,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=2  # Timeout in seconds
)

# Function to calculate CRC16 for Modbus RTU
crc16 = crcmod.predefined.mkCrcFun('modbus')

def read_switch_status(slave_id, start_address):
    """
    Reads the time control switch status from a Modbus slave device.
    
    :param slave_id: ID of the Modbus slave
    :param start_address: Starting register address (0-based)
    :return: True if switch is ON, False if OFF, None if an error occurred
    """
    function_code = 0x03  # Function code for reading holding registers
    
    # Construct the request frame
    request = struct.pack('>B B H H', slave_id, function_code, start_address, 1)
    
    # Calculate CRC16
    crc = crc16(request)
    
    # Append CRC to the frame
    request += struct.pack('<H', crc)
    
    # Send the request frame to the slave device
    ser.write(request)
    
    # Expected response length
    response_length = 1 + 1 + 1 + 2 + 2  # 8 bytes response
    response = ser.read(response_length)
    
    if len(response) < response_length:
        print("Incomplete response received.")
        return None
    
    # Validate CRC in response
    received_crc = struct.unpack('<H', response[-2:])[0]
    calculated_crc = crc16(response[:-2])
    
    if received_crc != calculated_crc:
        print(f"CRC error: received {received_crc:04X}, expected {calculated_crc:04X}")
        return None
    
    # Extract the status from the second data byte (second byte of the first register)
    status_byte = response[4]
    
    # Check if the second least significant bit is set to 1 (switch is ON)
    if status_byte & 0x02:
        return True  # Switch is ON
    else:
        return False  # Switch is OFF

# Address calculation for "时间控制" (Time Control)
# Documentation says 40007, so use 40007 - 1 = 6 (0-based)
start_address = 40007 - 40001

# Read the switch status
status = read_switch_status(1, start_address)

if status is True:
    print("时间控制开关 (Time Control Switch) is ON.")
elif status is False:
    print("时间控制开关 (Time Control Switch) is OFF.")
else:
    print("Failed to read the switch status.")

# Close the serial connection
ser.close()