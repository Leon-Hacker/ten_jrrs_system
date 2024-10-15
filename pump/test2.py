import serial
import struct

def crc16(data: bytes):
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if (crc & 0x0001) != 0:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc

# Construct command to read 12 registers starting from address 0020H
command = bytes.fromhex('01 03 00 05 00 02')  # Up to this point, it's without CRC
crc = crc16(command)
command += struct.pack('<H', crc)
print(command.hex())
# Open the serial port
ser = serial.Serial(
    port='/dev/tty.usbserial-AB0PEOBW',  # Your identified port
    baudrate=9600,                       # Adjust based on your device specs
    parity=serial.PARITY_NONE,           # No parity
    stopbits=serial.STOPBITS_ONE,        # 1 stop bit
    bytesize=serial.EIGHTBITS,           # 8 data bits
    timeout=1                            # Timeout for reading response
)

# Send the command
ser.write(command)

# Read the response (12 registers * 2 bytes each + 5 overhead bytes)
response = ser.read(29)  # Expecting 29 bytes in response
print(response.hex())
# Close the serial port
ser.close()