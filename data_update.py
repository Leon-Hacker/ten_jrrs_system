import numpy as np
import time
import csv
import os
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QTimer, QThread, QTimer
import logging
from logging.handlers import RotatingFileHandler

# Configure a logger for the data update worker with size-based rotation
data_update_logger = logging.getLogger('data_update_worker')
data_update_handler = RotatingFileHandler(
    'logs/data_update_worker.log',
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=5,         # Keep up to 5 backup files
    encoding='utf-8'
)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
data_update_handler.setFormatter(formatter)
data_update_logger.addHandler(data_update_handler)
data_update_logger.setLevel(logging.INFO)

class DataUpdateWorker(QObject):
    plot_update_signal = Signal(dict)
    stopped = Signal()
    start_storing_signal = Signal()
    stop_storing_signal = Signal()
    initial_voltage_signal = Signal(float)
    update_electrolysis_volt_var = Signal(float)

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
        self.time_recording = 5*60*1000  # 5 minutes in milliseconds

        # Generate separate filenames with current time prefixes
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.voltage_storage_path = os.path.join(storage_dir, f"{self.timestamp}_voltage_output.csv")
        self.current_storage_path = os.path.join(storage_dir, f"{self.timestamp}_current_output.csv")
        self.multichannel_voltage_path = os.path.join(storage_dir, f"{self.timestamp}_multichannel_voltage_output.csv")
        self.reactor_inlet_pressure_path = os.path.join(storage_dir, f"{self.timestamp}_reactor_inlet_pressure_output.csv")
        self.pump_flow_rate_path = os.path.join(storage_dir, f"{self.timestamp}_pump_flow_rate_output.csv")
        self.storage_dir = storage_dir

        # To accumulate data before storing to CSV
        self.ps_voltage_data = []
        self.time_data_voltage = []
        self.ps_current_data = []
        self.time_data_current = []
        self.multichannel_voltage_data = []
        self.time_data_multichannel_voltage = []
        self.pressure_data = []
        self.time_data_pressure = []
        self.flow_rate_data = []
        self.time_data_flow_rate = []

        # Ensure storage directory exists
        if not os.path.exists(storage_dir):
            os.makedirs(storage_dir)

    def start(self):
        """Start the timer to begin emitting data updates."""
        self.poll_timer = QTimer()  # Timer for real-time data updates
        self.poll_timer.setInterval(5000)  # Set interval to 5 seconds
        self.poll_timer.timeout.connect(self.update_data)
        self.poll_timer.start()

    def start_storing_data(self):
        """Start storing data to CSV files."""
        self.data_collection = True
        # Generate separate filenames with current time prefixes
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.voltage_storage_path = os.path.join(self.storage_dir, f"{self.timestamp}_voltage_output.csv")
        self.current_storage_path = os.path.join(self.storage_dir, f"{self.timestamp}_current_output.csv")
        self.multichannel_voltage_path = os.path.join(self.storage_dir, f"{self.timestamp}_multichannel_voltage_output.csv")
        self.reactor_inlet_pressure_path = os.path.join(self.storage_dir, f"{self.timestamp}_reactor_inlet_pressure_output.csv")
        self.pump_flow_rate_path = os.path.join(self.storage_dir, f"{self.timestamp}_pump_flow_rate_output.csv")

    def stop_storing_data(self):
        """Stop storing data to CSV files."""
        self.store_data_to_csv("voltage")
        self.store_data_to_csv("current")
        self.store_data_to_csv("multichannel_voltage")
        self.store_data_to_csv("reactor inlet pressure")
        self.store_data_to_csv("flow_rate")
        self.data_collection = False

    def stop(self):
        """Stop data updates when the application is closing."""
        # Store any remaining data upon stopping
        self.store_data_to_csv("voltage")
        self.store_data_to_csv("current")
        self.store_data_to_csv("multichannel_voltage")
        self.store_data_to_csv("reactor inlet pressure")
        self.store_data_to_csv("flow_rate")
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

    def update_pressure(self, pressure, cur_time):
        """Update the pressure history with the new pressure value."""
        self.pressure_history = np.roll(self.pressure_history, -1)
        self.pressure_history[-1] = pressure

        if self.data_collection:
            # Accumulate time and pressure data
            self.time_data_pressure.append(cur_time)
            self.pressure_data.append(float(pressure))
            
            # Check if we have 10 data points for storage
            if len(self.pressure_data) >= 100:
                self.store_data_to_csv("reactor inlet pressure")

    def update_voltages(self, voltages, cur_time):
        """Update the voltage history for multiple channels and store data periodically."""
        self.voltage_data = np.roll(self.voltage_data, -1, axis=1)
        self.voltage_data[:, -1] = voltages
        
        if self.data_collection:
            # Accumulate time and voltage data for all channels
            self.time_data_multichannel_voltage.append(cur_time)
            self.multichannel_voltage_data.append(voltages.copy())
            
            # Check if we have 10 data points for storage
            if len(self.multichannel_voltage_data) >= 100:
                self.store_data_to_csv("multichannel_voltage")

    def collect_inital_voltage(self):
        """After 10 minutes, collect initial average voltage data for the first run."""
        QTimer.singleShot(600000, self.calculate_initial_voltage)

    def calculate_initial_voltage(self):
        """Add and average the voltages of all channels greater than 1.5V in the past five minutes"""
        # Calculate the average voltage for each channel
        avg_voltages = np.mean(self.voltage_data[:, -300:], axis=1)
        valid_voltages = avg_voltages[avg_voltages > 1.5]
        if valid_voltages.size > 0:
            initial_voltage = np.mean(valid_voltages)
            self.initial_voltage_signal.emit(initial_voltage)
            data_update_logger.info(f"Initial voltage calculated: {initial_voltage} V")
            # Start updating the voltage change during the electrolysis process every 3 minutes 
            QTimer.singleShot(self.time_recording, self.update_voltage_change)
        else:
            data_update_logger.error("Failed to calculate initial voltage: size < 0")
    
    def update_voltage_change(self):
        """Calculate the voltage change during the electrolysis process every 5 minutes."""
        # Calculate the average voltage for each channel
        avg_voltages = np.mean(self.voltage_data[:, -300:], axis=1)
        valid_voltages = avg_voltages[avg_voltages > 1.5]
        if valid_voltages.size > 0:
            avg_voltage = np.mean(valid_voltages)
            self.update_electrolysis_volt_var.emit(avg_voltage)
            data_update_logger.info(f"Voltage change calculated: {avg_voltage} V")
            # Continue updating the voltage change every 5 minutes
            if self.data_collection:
                QTimer.singleShot(self.time_recording, self.update_voltage_change)
        else:
            data_update_logger.error("Failed to update voltage change: size < 0")
            if self.data_collection:
                QTimer.singleShot(self.time_recording, self.update_voltage_change)

    def update_flow_rate(self, flow_rate, cur_time):
        """Update the flow rate history with the new flow rate value."""
        self.flow_rate = np.roll(self.flow_rate, -1)
        self.flow_rate[-1] = flow_rate

        if self.data_collection:
            # Accumulate time and flow rate data
            self.time_data_flow_rate.append(cur_time)
            self.flow_rate_data.append(float(flow_rate))
            
            # Check if we have 10 data points for storage
            if len(self.flow_rate_data) >= 100:
                self.store_data_to_csv("flow_rate")

    def update_ps_current(self, current, cur_time):
        """Update the power supply current history with the new current value and store data periodically."""
        self.ps_current = np.roll(self.ps_current, -1)
        self.ps_current[-1] = current
        
        if self.data_collection:
            # Accumulate time and current data
            self.time_data_current.append(cur_time)
            self.ps_current_data.append(float(current))
            
            # Check if we have 10 data points for storage
            if len(self.ps_current_data) >= 100:
                self.store_data_to_csv("current")

    def update_ps_voltage(self, voltage, cur_time):
        """Update the power supply voltage history with the new voltage value and store data periodically."""
        self.ps_voltage = np.roll(self.ps_voltage, -1)
        self.ps_voltage[-1] = voltage
        
        if self.data_collection:
            # Accumulate time and voltage data
            self.time_data_voltage.append(cur_time)
            self.ps_voltage_data.append(float(voltage))
            
            # Check if we have 10 data points for storage
            if len(self.ps_voltage_data) >= 100:
                self.store_data_to_csv("voltage")

    def store_data_to_csv(self, data_type):
        """Store accumulated data to separate CSV files for each data type."""
        if data_type == "voltage" and self.ps_voltage_data:
            data = list(zip(self.time_data_voltage, self.ps_voltage_data))
            header = ['Timestamp', 'PS Voltage']
            path = self.voltage_storage_path
            self.time_data_voltage.clear()
            self.ps_voltage_data.clear()
        
        elif data_type == "current" and self.ps_current_data:
            data = list(zip(self.time_data_current, self.ps_current_data))
            header = ['Timestamp', 'PS Current']
            path = self.current_storage_path
            self.time_data_current.clear()
            self.ps_current_data.clear()

        elif data_type == "multichannel_voltage" and self.multichannel_voltage_data:
            # Combine the timestamp with voltage data for 10 channels
            data = [([time] + list(voltage)) for time, voltage in zip(self.time_data_multichannel_voltage, self.multichannel_voltage_data)]
            header = ['Timestamp'] + [f'Channel_{i+1}' for i in range(self.voltage_data.shape[0])]
            path = self.multichannel_voltage_path
            self.time_data_multichannel_voltage.clear()
            self.multichannel_voltage_data.clear()
        
        elif data_type == "reactor inlet pressure" and self.pressure_data:
            data = list(zip(self.time_data_pressure, self.pressure_data))
            header = ['Timestamp', 'Reactor Inlet Pressure']
            path = self.reactor_inlet_pressure_path
            self.time_data_pressure.clear()
            self.pressure_data.clear()

        elif data_type == "flow_rate" and self.flow_rate_data:
            data = list(zip(self.time_data_flow_rate, self.flow_rate_data))
            header = ['Timestamp', 'Flow Rate']
            path = self.pump_flow_rate_path
            self.time_data_flow_rate.clear()
            self.flow_rate_data.clear()
        
        else:
            return  # No data to store

        # Append data to the specified CSV file
        with open(path, mode='a', newline='') as file:
            writer = csv.writer(file)
            if file.tell() == 0:  # Add headers if the file is new
                writer.writerow(header)
            writer.writerows(data)
