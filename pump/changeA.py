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
    timeout=5  # Increased timeout for more reliable communication
)

# Function to calculate CRC16 for Modbus RTU
crc16 = crcmod.predefined.mkCrcFun('modbus')

def write_holding_registers(slave_id, start_address, values):
    """
    Writes values to multiple Modbus holding registers.
    
    :param slave_id: ID of the Modbus slave
    :param start_address: Starting register address (0-based)
    :param values: List of values to write (as 16-bit integers)
    :return: True if successful, False otherwise
    """
    function_code = 0x10  # Function code for writing multiple registers
    num_registers = len(values)
    byte_count = num_registers * 2  # Each register is 2 bytes
    
    # Construct the request frame
    request = struct.pack('>B B H H B', slave_id, function_code, start_address, num_registers, byte_count)
    
    # Pack the values into the request frame
    request += struct.pack('>' + 'H' * num_registers, *values)
    
    # Calculate CRC16
    crc = crc16(request)
    
    # Append CRC to the frame
    request += struct.pack('<H', crc)
    print("Sent:", request.hex())
    
    # Send the request frame to the slave device
    ser.write(request)
    
    # Expected response length: 1 byte Slave ID + 1 byte Function Code + 2 bytes Start Address + 2 bytes Quantity + 2 bytes CRC
    response_length = 8
    response = ser.read(response_length)
    print("Received:", response.hex())
    
    if len(response) < response_length:
        print("Incomplete response received.")
        return False
    
    # Validate CRC in response
    received_crc = struct.unpack('<H', response[-2:])[0]
    calculated_crc = crc16(response[:-2])
    
    if received_crc != calculated_crc:
        print(f"CRC error: received {received_crc:04X}, expected {calculated_crc:04X}")
        return False
    
    return True

# Address for itinerary is 40055, so 40055 - 40001 = 54 (0-based address)
itinerary_address = 40055 - 40001

# The stroke value you want to write (range 0-100)
stroke_value = 50  # Example value, you can modify this

# Convert the stroke value to 32-bit float and split into two 16-bit registers
stroke_registers = struct.unpack('>HH', struct.pack('>f', stroke_value))

# Write the stroke value (as two 16-bit registers) to the itinerary register
if write_holding_registers(1, itinerary_address, stroke_registers):
    print(f"Successfully set the pump stroke to {stroke_value}%.")
else:
    print("Failed to set the pump stroke.")

# Close the serial connection
ser.close()
