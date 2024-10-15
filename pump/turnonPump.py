import serial
import struct
import crcmod
import time

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

def write_pump_status(slave_id, address, status):
    """
    Controls the pump by writing the status to the specified register.
    
    :param slave_id: Modbus slave ID
    :param address: Register address to write the status to (0-based)
    :param status: The status byte to write (0x05 = start, 0x00 = stop, 0x06 = pause)
    :return: True if successful, False otherwise
    """
    function_code = 0x06  # Function code for writing a single holding register
    
    # Construct the request frame (write the status byte as the register value)
    request = struct.pack('>B B H H', slave_id, function_code, address, status)
    
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

# Address for controlling the pump
register_address = 40006 - 40001  # Convert to 0-based address

# Example: Start the pump (write 0x05 to the control register)
if write_pump_status(1, register_address, 0x0500):
    print("Pump started successfully.")

# Example: Pause the pump (write 0x06 to the control register)
if write_pump_status(1, register_address, 0x0600):
    print("Pump paused successfully.")
time.sleep(10)
# Example: Stop the pump (write 0x00 to the control register)
if write_pump_status(1, register_address, 0x0000):
    print("Pump stopped successfully.")

# Close the serial connection
ser.close()