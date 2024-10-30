import numpy as np
import time
import csv
import os
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QTimer

class DataUpdateWorker(QObject):
    plot_update_signal = Signal(dict)
    stopped = Signal()
    start_stroing_signal = Signal()
    stop_storing_signal = Signal()

    def __init__(self, pressure_history_size=600, voltage_channels=10, storage_dir="D:\\python\\data"):
        super().__init__()
        self.pressure_history = np.zeros(pressure_history_size)  # Store 10 minutes of data (600 seconds)
        self.voltage_data = np.zeros((voltage_channels, pressure_history_size))  # Voltage for multiple channels
        self.flow_rate = np.zeros(pressure_history_size)  # Store 10 minutes of data (600 seconds)
        self.ps_current = np.zeros(pressure_history_size)  # Store 10 minutes of data (600 seconds)
        self.ps_voltage = np.zeros(pressure_history_size)
        self.running = True
        self.poll_timer = None
        self.data_collection = False

        # Generate separate filenames with current time prefixes
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.voltage_storage_path = os.path.join(storage_dir, f"{self.timestamp}_voltage_output.csv")
        self.current_storage_path = os.path.join(storage_dir, f"{self.timestamp}_current_output.csv")
        self.storage_dir = storage_dir

        # To accumulate data before storing to CSV
        self.ps_voltage_data = []
        self.time_data_voltage = []
        self.ps_current_data = []
        self.time_data_current = []

        # Ensure storage directory exists
        if not os.path.exists(storage_dir):
            os.makedirs(storage_dir)

    def start(self):
        """Start the timer to begin emitting data updates."""
        self.poll_timer = QTimer()  # Timer for real-time data updates
        self.poll_timer.setInterval(5000)  # Set interval to 5 seconds
        self.poll_timer.timeout.connect(self.update_data)
        self.poll_timer.start()

    def start_stroing_data(self):
        """Start storing data to CSV files."""
        self.data_collection = True
        # Generate separate filenames with current time prefixes
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.voltage_storage_path = os.path.join(self.storage_dir, f"{self.timestamp}_voltage_output.csv")
        self.current_storage_path = os.path.join(self.storage_dir, f"{self.timestamp}_current_output.csv")

    def stop_storing_data(self):
        """Stop storing data to CSV files."""
        self.store_data_to_csv("voltage")
        self.store_data_to_csv("current")
        self.data_collection = False

    def stop(self):
        """Stop data updates when the application is closing."""
        # Store any remaining data upon stopping
        self.store_data_to_csv("voltage")
        self.store_data_to_csv("current")
        self.running = False
        self.data_collection = False

    def update_data(self):
        """Emit both pressure and voltage data as a dictionary periodically."""
        if not self.running:
            self.poll_timer.stop()
            return

        data = {
            'pressure': self.pressure_history,
            'voltages': self.voltage_data,
            'flow_rate': self.flow_rate,
            'ps_current': self.ps_current,
            'ps_voltage': self.ps_voltage,
        }
        self.plot_update_signal.emit(data)

    def update_pressure(self, pressure):
        """Update the pressure history with the new pressure value."""
        self.pressure_history = np.roll(self.pressure_history, -1)
        self.pressure_history[-1] = pressure

    def update_voltages(self, voltages):
        """Update the voltage history for multiple channels."""
        self.voltage_data = np.roll(self.voltage_data, -1, axis=1)
        self.voltage_data[:, -1] = voltages

    def update_flow_rate(self, flow_rate):
        """Update the flow rate history with the new flow rate value."""
        self.flow_rate = np.roll(self.flow_rate, -1)
        self.flow_rate[-1] = flow_rate

    def update_ps_current(self, current, cur_time):
        """Update the power supply current history with the new current value and store data periodically."""
        self.ps_current = np.roll(self.ps_current, -1)
        self.ps_current[-1] = current
        
        if self.data_collection:
            # Accumulate time and current data
            self.time_data_current.append(cur_time)
            self.ps_current_data.append(float(current))
            
            # Check if we have 100 data points for storage
            if len(self.ps_current_data) >= 10:
                self.store_data_to_csv("current")

    def update_ps_voltage(self, voltage, cur_time):
        """Update the power supply voltage history with the new voltage value and store data periodically."""
        self.ps_voltage = np.roll(self.ps_voltage, -1)
        self.ps_voltage[-1] = voltage
        
        if self.data_collection:
            # Accumulate time and voltage data
            self.time_data_voltage.append(cur_time)
            self.ps_voltage_data.append(float(voltage))
            
            # Check if we have 100 data points for storage
            if len(self.ps_voltage_data) >= 10:
                self.store_data_to_csv("voltage")

    def store_data_to_csv(self, data_type):
        """Store the accumulated time and ps_voltage or ps_current data to separate CSV files."""
        if data_type == "voltage" and self.ps_voltage_data:
            # Prepare voltage data
            data = list(zip(self.time_data_voltage, self.ps_voltage_data))
            header = ['Timestamp', 'PS Voltage']
            path = self.voltage_storage_path
            self.time_data_voltage.clear()
            self.ps_voltage_data.clear()
        elif data_type == "current" and self.ps_current_data:
            # Prepare current data
            data = list(zip(self.time_data_current, self.ps_current_data))
            header = ['Timestamp', 'PS Current']
            path = self.current_storage_path
            self.time_data_current.clear()
            self.ps_current_data.clear()
        else:
            return  # No data to store

        # Append data to the specified CSV file
        with open(path, mode='a', newline='') as file:
            writer = csv.writer(file)
            if file.tell() == 0:  # Add headers if the file is new
                writer.writerow(header)
            writer.writerows(data)
