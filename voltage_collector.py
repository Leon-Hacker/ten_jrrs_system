import serial
import struct
import time
import logging
from PySide6.QtCore import QThread, Signal

# Configure a logger for the voltage collector
voltage_logger = logging.getLogger('VoltageCollector')
voltage_handler = logging.FileHandler('voltage_collector.log')
voltage_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
voltage_logger.addHandler(voltage_handler)
voltage_logger.setLevel(logging.INFO)

class VoltageCollector:
    def __init__(self, port='COM5', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.command = self.build_command()
        voltage_logger.info("VoltageCollector initialized with port %s, baudrate %d", port, baudrate)

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
        """Open the serial connection to the voltage collector."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=1
            )
            voltage_logger.info("Opened connection on port %s", self.port)
        except serial.SerialException as e:
            voltage_logger.error("Failed to open connection on port %s: %s", self.port, str(e))

    def close_connection(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            voltage_logger.info("Closed connection on port %s", self.port)

    def read_voltages(self):
        """Read voltage values from the device."""
        if not self.ser or not self.ser.is_open:
            self.open_connection()

        self.ser.reset_input_buffer()
        self.ser.write(self.command)
        voltage_logger.info("Sent read command to voltage collector.")

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
            voltage_logger.info("Read voltages: %s", voltages[:10])
            return voltages[:10]  # Return only the first 10 voltages
        else:
            voltage_logger.warning("Incomplete response received for voltage read.")
            return None

# Thread to run the voltage collection in the background
class VoltageCollectorThread(QThread):
    voltages_updated = Signal(list, float)  # Signal to send the voltage data to the GUI

    def __init__(self, voltage_collector, parent=None):
        super().__init__(parent)
        self.voltage_collector = voltage_collector
        self.running = True

    def run(self):
        """Main loop for collecting voltages."""
        while self.running:
            try:
                voltages = self.voltage_collector.read_voltages()
                cur_time = time.time()
                self.voltages_updated.emit(voltages, cur_time)  # Emit the signal to update GUI
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