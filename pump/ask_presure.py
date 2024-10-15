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

def read_holding_registers(slave_id, start_address, num_registers):
    """
    Reads holding registers from a Modbus slave device.
    
    :param slave_id: ID of the Modbus slave
    :param start_address: Starting register address (0-based)
    :param num_registers: Number of registers to read
    :return: List of register values if successful, None if an error occurred
    """
    function_code = 0x03  # Function code for reading holding registers
    
    # Construct the request frame
    request = struct.pack('>B B H H', slave_id, function_code, start_address, num_registers)
    
    # Calculate CRC16
    crc = crc16(request)
    
    # Append CRC to the frame
    request += struct.pack('<H', crc)
    
    # Send the request frame to the slave device
    ser.write(request)
    
    # Expected response: 1 byte Slave ID + 1 byte Function Code + 1 byte Byte Count + data + 2 bytes CRC
    response_length = 1 + 1 + 1 + 2 * num_registers + 2
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
    print(response.hex())
    # Extract data (response[3:-2] skips the ID, function code, and byte count)
    data = response[3:-2]
    registers = struct.unpack('>' + 'H' * num_registers, data)
    print(registers)
    return registers

# Address calculations for "瞬时流量" (Instantaneous Flow)
# Documentation says 40053, so use 40053 - 1 = 52 (0-based)
start_address = 40073 - 40001

# Read 2 registers (32-bit float)
registers = read_holding_registers(1, start_address, 2)

if registers:
    # Convert the two 16-bit registers into a 32-bit float
    instantaneous_flow = struct.unpack('>f', struct.pack('>HH', *registers))[0]
    print(f"瞬时流量 (Instantaneous Flow): {instantaneous_flow} units")
else:
    print("Failed to read instantaneous flow.")

# Close the serial connection
ser.close()