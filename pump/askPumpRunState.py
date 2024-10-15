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

def read_pump_status(slave_id, start_address):
    """
    Reads the pump status from a Modbus slave device.
    
    :param slave_id: ID of the Modbus slave
    :param start_address: Starting register address (0-based)
    :return: Pump status as a string ('start', 'pause', 'stop') or None if an error occurred
    """
    function_code = 0x03  # Function code for reading holding registers
    num_registers = 2     # Reading two registers
    
    # Construct the request frame
    request = struct.pack('>B B H H', slave_id, function_code, start_address, num_registers)
    
    # Calculate CRC16
    crc = crc16(request)
    
    # Append CRC to the frame
    request += struct.pack('<H', crc)
    
    # Send the request frame
    ser.write(request)
    
    # Expected response length: 1 byte Slave ID + 1 byte Function Code + 1 byte Byte Count + 4 bytes Data + 2 bytes CRC
    response_length = 1 + 1 + 1 + 4 + 2
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
    
    # Extract the first byte of data to determine the pump status
    status_byte = response[3]  # The first byte of the data
    
    if status_byte == 0x05:
        return "start"
    elif status_byte == 0x06:
        return "pause"
    elif status_byte == 0x00:
        return "stop"
    else:
        print(f"Unknown status byte: {status_byte:02X}")
        return None

# Address for reading pump status
start_address = 5  # Address 0005 in 0-based index

# Read the pump status
status = read_pump_status(1, start_address)

if status:
    print(f"Pump status: {status}")
else:
    print("Failed to read pump status.")

# Close the serial connection
ser.close()