import serial
import struct
import time
from PySide6.QtCore import QThread, Signal

class VoltageCollector:
    def __init__(self, port='COM5', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.command = self.build_command()

    def build_command(self):
        # Construct command to read 12 registers starting from address 0020H
        command = bytes.fromhex('01 03 00 20 00 0C')
        crc = self.crc16(command)
        command += struct.pack('<H', crc)
        return command

    def crc16(self, data: bytes):
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

    def open_connection(self):
        # Open the serial port
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1
        )

    def close_connection(self):
        # Close the serial port
        if self.ser and self.ser.is_open:
            self.ser.close()

    def read_voltages(self):
        if not self.ser or not self.ser.is_open:
            self.open_connection()
        
        self.ser.reset_input_buffer()

        # Send the command
        self.ser.write(self.command)

        # Add delay to allow sensor time to process the command
        time.sleep(0.05)  # 50 ms delay

        # Read the response (12 registers * 2 bytes each + 5 overhead bytes)
        response = self.ser.read(29)  # Expecting 29 bytes in response

        voltages = []
        if len(response) == 29:
            for i in range(12):
                voltage_raw = int.from_bytes(response[3 + 2 * i:5 + 2 * i], byteorder='big', signed=True)
                voltage = voltage_raw * 30 / 10000 * (-1)  # Scale according to the 30V range
                voltages.append(voltage)
        return voltages[:10]  # Return only the first 10 voltages


# Thread to run the voltage collection in the background
class VoltageCollectorThread(QThread):
    voltages_updated = Signal(list)  # Signal to send the voltage data to the GUI

    def __init__(self, voltage_collector, parent=None):
        super().__init__(parent)
        self.voltage_collector = voltage_collector
        self.running = True

    def run(self):
        """Main loop for collecting voltages."""
        while self.running:
            try:
                voltages = self.voltage_collector.read_voltages()
                self.voltages_updated.emit(voltages)  # Emit the signal to update GUI
            except Exception as e:
                print(f"Error reading voltages: {e}")
            self.msleep(1000)  # Sleep for 1000 ms between voltage readings

    def stop(self):
        """Stop the thread."""
        self.running = False
        self.wait()  # Wait for the thread to finish


# Example usage
if __name__ == "__main__":
    vc = VoltageCollector()
    vc_thread = VoltageCollectorThread(vc)

    vc_thread.start()
    # ... add additional logic for stopping the thread, using the voltages, etc.