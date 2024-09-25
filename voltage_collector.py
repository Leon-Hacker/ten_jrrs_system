import serial
import struct

class VoltageCollector:
    def __init__(self, port='/dev/tty.usbserial-130', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

    def open(self):
        """Open the serial connection."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=1
            )
            return True
        except Exception as e:
            print(f"Failed to open port: {e}")
            return False

    def close(self):
        """Close the serial connection."""
        if self.ser:
            self.ser.close()

    def crc16(self, data: bytes):
        """Calculate the CRC16 checksum."""
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

    def read_voltages(self):
        """Read voltages from the 12 channels."""
        command = bytes.fromhex('01 03 00 20 00 0C')
        crc = self.crc16(command)
        command += struct.pack('<H', crc)

        if not self.ser:
            print("Serial port not open.")
            return None

        try:
            # Send the command
            self.ser.write(command)

            # Read the response (12 registers * 2 bytes each + 5 overhead bytes)
            response = self.ser.read(29)  # Expecting 29 bytes in response

            if len(response) == 29:
                voltages = []
                for i in range(12):
                    voltage_raw = int.from_bytes(response[3 + 2*i:5 + 2*i], byteorder='big', signed=True)
                    voltage = voltage_raw * 30 / 10000  # Scale according to the 30V range
                    voltages.append(voltage)
                return voltages
            else:
                print("Invalid response length")
                return None
        except Exception as e:
            print(f"Error reading voltages: {e}")
            return None