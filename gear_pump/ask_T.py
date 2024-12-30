import serial
import struct

def read_modbus_temperature(port, baudrate=9600, timeout=1):
    # Configure the serial port
    ser = serial.Serial(port, baudrate=baudrate, bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=timeout)
    try:
        # Modbus RTU read command
        # Slave ID: 1
        # Function code: 04 (Read Holding Registers)
        # Starting address: 3000 (D3000) -> 0x0BB8
        # Register count: 1
        request = struct.pack('>BBHH', 0x01, 0x03, 3010, 0x0001)
        
        # Calculate CRC
        crc = calculate_crc(request)
        request += struct.pack('<H', crc)
        
        # Send request
        ser.write(request)
        
        # Receive response
        response = ser.read(7)
        print(response)
        if len(response) < 7:
            raise Exception("Incomplete response received")

        # Parse response
        slave_id, function_code, byte_count = struct.unpack('>BBB', response[:3])
        if function_code == 0x83:  # Exception response
            raise Exception(f"Modbus exception code: {response[2]}")

        # Extract data and calculate temperature
        data = struct.unpack('>H', response[3:5])[0]

        # Validate CRC
        received_crc = struct.unpack('<H', response[5:])[0]
        calculated_crc = calculate_crc(response[:-2])
        if calculated_crc != received_crc:
            raise Exception("CRC mismatch")

        return data
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
    port = 'COM20'
    temperature = read_modbus_temperature(port)
    if temperature is not None:
        print(f"Temperature: {temperature/10}°C")
