import serial
import struct

def read_modbus_current_flow(port, baudrate=9600, timeout=1):
    """
    Reads the current flow state from the Modbus device as ON (0x01) or OFF (0x00).
    """
    try:
        # Configure the serial port
        ser = serial.Serial(port, baudrate=baudrate, bytesize=serial.EIGHTBITS,
                            parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=timeout)
    except serial.SerialException as e:
        print(f"Error: Could not open serial port {port}. Details: {e}")
        return None

    try:
        # Modbus RTU read command
        # Slave ID: 1
        # Function code: 01 (Read Coils)
        # Starting address: 1075 (0x0433)
        # Quantity: 1 coil
        request = struct.pack('>BBHH', 0x01, 0x01, 0x0433, 0x0001)

        # Calculate CRC
        crc = calculate_crc(request)
        request += struct.pack('<H', crc)

        # Send request
        ser.write(request)
        print(f"Sent Request: {request.hex()}")

        # Receive response
        response = ser.read(6)  # Adjusted expected response length
        print(f"Received Response: {response.hex()}")

        if len(response) < 6:
            raise Exception("Incomplete response received. Check the device connection or configuration.")

        # Parse response
        slave_id, function_code, byte_count = struct.unpack('>BBB', response[:3])
        if function_code == 0x83:  # Exception response
            raise Exception(f"Modbus exception code: {response[2]}")

        # Extract the coil state (1 byte)
        coil_status = response[3]
        print(f"Raw Coil Status: {coil_status}")

        # Validate CRC
        received_crc = struct.unpack('<H', response[4:6])[0]
        calculated_crc = calculate_crc(response[:-2])
        if calculated_crc != received_crc:
            raise Exception("CRC mismatch")

        # Interpret coil status
        state = "ON" if coil_status == 0x01 else "OFF"
        return state

    except serial.SerialTimeoutException:
        print(f"Error: Timeout while communicating with the device on port {port}.")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None
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
    state = read_modbus_current_flow(port)
    if state is not None:
        print(f"Pump State: {state}")
    else:
        print("Failed to read pump state.")
