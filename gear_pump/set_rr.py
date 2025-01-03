import serial
import struct

def set_rotate_rate(port, rotate_rate, baudrate=9600, timeout=1):

    if not (0 <= rotate_rate <= 0xFFFF):
        raise ValueError("Rotate rate must be a 16-bit unsigned integer (0 to 65,535).")

    # Configure the serial port
    ser = serial.Serial(port, baudrate=baudrate, bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=timeout)
    try:
        # Modbus RTU write command
        # Slave ID: 1
        # Function code: 06 (Write Single Register)
        # Starting address: 1202 (0x04B2)
        register_address = 0x04B2  

        # Build the request
        request = struct.pack('>BBHH', 0x01, 0x06, register_address, rotate_rate)

        # Calculate CRC
        crc = calculate_crc(request)
        request += struct.pack('<H', crc)

        # Send request
        ser.write(request)
        print(f"Sent Request: {request.hex()}")

        # Receive response (should be 8 bytes)
        response = ser.read(8)
        if len(response) < 8:
            raise Exception("Incomplete response received")

        print(f"Received Response: {response.hex()}")

        # Validate response
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = calculate_crc(response[:-2])
        if calculated_crc != received_crc:
            raise Exception("CRC mismatch")

        print(f"Rotate rate set to {rotate_rate} successfully.")
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
    port = 'COM20'  # Update with the correct COM port
    rotate_rate = int(input("Enter the rotate rate to set: "))
    set_rotate_rate(port, rotate_rate)
