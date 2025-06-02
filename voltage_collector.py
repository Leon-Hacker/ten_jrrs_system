import serial
import struct
import time
import logging
from PySide6.QtCore import QThread, Signal, QObject, QTimer, QMutex, QMutexLocker
from logging.handlers import RotatingFileHandler

# Configure a logger for the voltage collector
voltage_logger = logging.getLogger('VoltageCollector')
voltage_handler = RotatingFileHandler(
    'logs/voltage_collector.log',
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=5,
    encoding='utf-8'
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
voltage_handler.setFormatter(formatter)
voltage_logger.addHandler(voltage_handler)
voltage_logger.setLevel(logging.INFO)

class VoltageCollector:
    def __init__(self, port='COM7', baudrate=115200):
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
            voltage_logger.info("Read voltages: %s", voltages[:11])
            voltages[5] = voltages[10]  # Channel 6 is damaged, so we replace it with channel 11
            # voltages = [-1*i for i in voltages]
            return voltages[:10]  # Return only the first 10 voltages, with channel 6 replaced by channel 11.
        else:
            voltage_logger.warning("Incomplete response received for voltage read.")
            return None

class VoltageCollectorWorker(QObject):
    # ----------------------
    #        SIGNALS
    # ----------------------
    voltages_updated = Signal(list, float)  # Signal to send the voltage data to the GUI
    stopped = Signal()  # Signal to indicate that the worker has stopped

    # ----------------------
    #        INIT
    # ----------------------
    def __init__(self, voltage_collector, parent=None):
        """
        Worker class to handle voltage collection in a separate thread.

        :param voltage_collector: An instance responsible for reading voltages.
        :param parent: Optional parent QObject.
        """
        super().__init__(parent)
        self.voltage_collector = voltage_collector
        self.running = True
        self.mutex = QMutex()
        self.timer = None
        self.cur_voltages = None

    # ----------------------
    #   START COLLECTING
    # ----------------------
    def start_collecting(self):
        """
        Start the voltage collection process by starting the QTimer.
        This method should be connected to the thread's started signal.
        """
        # Initialize QTimer for periodic voltage collection
        self.timer = QTimer()
        self.timer.setInterval(1000)  # 1000 ms = 1 second
        self.timer.timeout.connect(self.collect_voltage)
        self.timer.start()
    # ----------------------
    #   STOP COLLECTING
    # ----------------------
    def stop_collecting(self):
        """
        Stop the voltage collection process by stopping the QTimer.
        """
        self.running = False

    # ----------------------
    #   COLLECT VOLTAGE
    # ----------------------
    def collect_voltage(self):
        """
        Collect voltage data and emit the voltages_updated signal.
        """
        if not self.running:
            self.timer.stop()
            return
        
        with QMutexLocker(self.mutex):
            try:
                voltages = self.voltage_collector.read_voltages()
                cur_time = time.time()
                self.voltages_updated.emit(voltages, cur_time)
            except Exception as e:
                print(f"Error reading voltages: {e}")
