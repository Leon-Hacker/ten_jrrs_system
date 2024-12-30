import serial
import struct

def set_pump_state(port, state, baudrate=9600, timeout=1):
    """
    Sets the pump state to ON or OFF by writing to three registers:
    1100, 1101, and 1102 using Modbus Function Code 16.

    :param port: COM port (e.g., 'COM20')
    :param state: 1 to turn ON, 0 to turn OFF
    :param baudrate: Baud rate for the serial communication
    :param timeout: Timeout for the serial port
    """
    # State validation
    if state not in [0, 1]:
        raise ValueError("State must be 0 (OFF) or 1 (ON).")

    # Define register addresses and values
    register_address = 1100  # Starting address (1100)
    register_count = 3       # Writing to 3 registers

    # Register values based on state
    if state == 1:  # Pump START
        values = [1, 0, 0]  # 1100=1, 1101=0, 1102=0
    else:           # Pump STOP
        values = [0, 0, 1]  # 1100=0, 1101=0, 1102=1

    # Build the request
    request = struct.pack('>BBHHB', 0x01, 0x10, register_address, register_count, register_count * 2)
    for value in values:
        request += struct.pack('>H', value)  # Append each 16-bit register value

    # Calculate CRC
    crc = calculate_crc(request)
    request += struct.pack('<H', crc)

    # Configure the serial port
    ser = serial.Serial(port, baudrate=baudrate, bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=timeout)
    try:
        # Send request
        ser.write(request)
        print(f"Sent Request: {request.hex()}")

        # Receive response (should be 8 bytes)
        response = ser.read(8)
        if len(response) < 8:
            raise Exception("Incomplete response received")

        print(f"Received Response: {response.hex()}")

        # Validate CRC
        received_crc = struct.unpack('<H', response[-2:])[0]
        calculated_crc = calculate_crc(response[:-2])
        if calculated_crc != received_crc:
            raise Exception("CRC mismatch")

        print(f"Pump state set to {'ON' if state == 1 else 'OFF'} successfully.")
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
    state = int(input("Enter pump state (1 for ON, 0 for OFF): "))
    set_pump_state(port, state)
