import serial
import struct

def set_pump_state(port, state, baudrate=9600, timeout=1):
    """
    Sets the pump state to ON (1) or OFF (0) using Modbus Function Code 06.

    :param port: COM port (e.g., 'COM20')
    :param state: 1 to turn ON, 0 to turn OFF
    :param baudrate: Baud rate for the serial communication
    :param timeout: Timeout for the serial port
    """
    if state not in [0, 1]:
        raise ValueError("State must be 0 (OFF) or 1 (ON).")

    # Configure the serial port
    ser = serial.Serial(port, baudrate=baudrate, bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=timeout)
    try:
        # Modbus RTU write command
        # Slave ID: 1
        # Function code: 06 (Write Single Register)
        # Register address: 1100, 1101, 1102
        # Value to write: state (1 or 0)
        register_address = 1100  
        request = struct.pack('>BBHH', 0x01, 0x06, register_address, state)
        
        # Calculate CRC
        crc = calculate_crc(request)
        request += struct.pack('<H', crc)
        
        # Send request
        ser.write(request)
        
        # Receive response (should be identical to the request if successful)
        response = ser.read(8)
        if len(response) < 8:
            raise Exception("Incomplete response received")

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
    port = 'COM20'  # Update if your COM port is different
    state = int(input("Enter pump state (1 for ON, 0 for OFF): "))
    set_pump_state(port, state)
