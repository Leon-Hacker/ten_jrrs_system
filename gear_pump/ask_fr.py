import serial
import struct

def read_modbus_current_flow(port, baudrate=9600, timeout=1):
    """
    Reads the current flow rate from the Modbus device as a 16-bit unsigned integer.
    """
    # Configure the serial port
    ser = serial.Serial(
        port, 
        baudrate=baudrate, 
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE, 
        stopbits=serial.STOPBITS_ONE, 
        timeout=timeout
    )
    try:
        # Modbus RTU read command
        # Slave ID: 1
        # Function code: 03 (Read Holding Registers)
        # Starting address: 1214 (0x04BE)
        # Register count: 1 (for 16-bit unsigned data)
        request = struct.pack('>BBHH', 0x01, 0x03, 0x04BE, 0x0001)
        
        # Calculate CRC
        crc = calculate_crc(request)
        request += struct.pack('<H', crc)
        print(f"Request Bytes: {request}")
        
        # Send request
        ser.write(request)
        print(f"Sent Request: {request.hex()}")

        # Receive response (7 bytes expected for 1 register)
        response = ser.read(7)
        print(f"Raw Response: {response}")
        
        if len(response) < 7:
            raise Exception("Incomplete response received")

        print(f"Received Response: {response.hex()}")

        # Parse response header
        slave_id, function_code, byte_count = struct.unpack('>BBB', response[:3])
        
        if function_code == 0x83:  # Exception response
            exception_code = response[3]
            raise Exception(f"Modbus exception code: {exception_code}")

        if byte_count != 2:
            raise Exception(f"Unexpected byte count: {byte_count}")

        # Extract 16-bit unsigned integer data
        unsigned_data = struct.unpack('>H', response[3:5])[0]  # '>H' for big-endian 16-bit unsigned integer

        # Validate CRC
        received_crc = struct.unpack('<H', response[5:7])[0]
        calculated_crc = calculate_crc(response[:-2])
        if calculated_crc != received_crc:
            raise Exception("CRC mismatch")

        return unsigned_data
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ser.close()

def calculate_crc(data):
    """Calculate Modbus CRC16."""
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

if __name__ == '__main__':
    port = 'COM20'  # Update if your COM port is different
    current_flow = read_modbus_current_flow(port)
    if current_flow is not None:
        print(f"Current Flow: {current_flow} mL/min")
