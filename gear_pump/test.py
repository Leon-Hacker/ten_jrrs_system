import serial
import struct

def read_pump_state(port, baudrate=9600, timeout=1):
    """
    Reads the states of registers 1100, 1101, and 1102 using Modbus Function Code 03.

    :param port: COM port (e.g., 'COM20')
    :param baudrate: Baud rate for the serial communication
    :param timeout: Timeout for serial communication
    :return: A tuple containing the states of registers 1100, 1101, and 1102
    """
    # Configure the serial port
    ser = serial.Serial(port, baudrate=baudrate, bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=timeout)
    try:
        # Modbus RTU read command
        # Slave ID: 1
        # Function code: 03 (Read Holding Registers)
        # Starting address: 1100 (0x044C)
        # Register count: 3
        register_address = 0x044C  # 1100 in hexadecimal
        register_count = 3

        # Build the request
        request = struct.pack('>BBHH', 0x01, 0x03, register_address, register_count)

        # Calculate CRC
        crc = calculate_crc(request)
        request += struct.pack('<H', crc)

        # Send request
        ser.write(request)
        print(f"Sent Request: {request.hex()}")

        # Receive response (should be 11 bytes: 1-byte Slave ID, 1-byte Function Code, 1-byte Byte Count, 3x 2-byte Register Values, 2-byte CRC)
        response = ser.read(11)
        if len(response) < 11:
            raise Exception("Incomplete response received")

        print(f"Received Response: {response.hex()}")

        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = calculate_crc(response[:-2])
        if calculated_crc != received_crc:
            raise Exception("CRC mismatch")

        # Parse the register values
        _, _, byte_count = struct.unpack('>BBB', response[:3])
        if byte_count != 6:  # 3 registers x 2 bytes each
            raise Exception("Unexpected byte count in response")

        reg_1100, reg_1101, reg_1102 = struct.unpack('>HHH', response[3:9])
        return reg_1100, reg_1101, reg_1102

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
    port = 'COM20'  # Update with the correct COM port
    states = read_pump_state(port)
    if states:
        reg_1100, reg_1101, reg_1102 = states
        print(f"Register 1100 State: {reg_1100}")
        print(f"Register 1101 State: {reg_1101}")
        print(f"Register 1102 State: {reg_1102}")

        # Interpret pump state
        if reg_1100 == 0 and reg_1101 == 0 and reg_1102 == 1:
            print("Pump is STOPPED")
        elif reg_1100 == 1 and reg_1101 == 0 and reg_1102 == 0:
            print("Pump is STARTED")
        else:
            print("Pump state is UNKNOWN")
