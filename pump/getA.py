import serial
import struct
import crcmod
import time
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
    
    # Extract data (response[3:-2] skips the ID, function code, and byte count)
    data = response[3:-2]
    registers = struct.unpack('>' + 'H' * num_registers, data)
    
    return registers

# Address calculations
# Instantaneous flow is at address 40051, so 40051 - 40001 = 50
flow_address = 40051 - 40001

# Real-time pressure is at address 40053, so 40053 - 40001 = 52
pressure_address = 40053 - 40001

# Itinerary is at address 40055, so 40055 - 40001 = 54
itinerary_address = 40055 - 40001

# Read instantaneous flow (2 registers for 32-bit float)
flow_registers = read_holding_registers(1, flow_address, 2)

if flow_registers:
    # Convert the two 16-bit registers into a 32-bit float for flow
    instantaneous_flow = struct.unpack('>f', struct.pack('>HH', *flow_registers))[0]
    print(f"Instantaneous flow: {instantaneous_flow} units")
else:
    print("Failed to read the instantaneous flow.")

time.sleep(0.05)
# Read real-time pressure (2 registers for 32-bit float)
pressure_registers = read_holding_registers(1, pressure_address, 2)

if pressure_registers:
    # Convert the two 16-bit registers into a 32-bit float for pressure
    real_time_pressure = struct.unpack('>f', struct.pack('>HH', *pressure_registers))[0]
    print(f"Real-time pressure: {real_time_pressure} units")
else:
    print("Failed to read the real-time pressure.")
    
time.sleep(0.05)
# Read itinerary (2 registers for 32-bit float)
itinerary_registers = read_holding_registers(1, itinerary_address, 2)

if itinerary_registers:
    # Convert the two 16-bit registers into a 32-bit float for itinerary
    itinerary_value = struct.unpack('>f', struct.pack('>HH', *itinerary_registers))[0]
    print(f"Itinerary: {itinerary_value} units")
else:
    print("Failed to read the itinerary.")

# Close the serial connection
ser.close()
