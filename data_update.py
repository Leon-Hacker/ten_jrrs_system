import numpy as np
from PySide6.QtCore import QThread, Signal

class DataUpdateThread(QThread):
    plot_update_signal = Signal(dict)

    def __init__(self, pressure_history_size=600, voltage_channels=10, parent=None):
        super().__init__(parent)
        self.pressure_history = np.zeros(pressure_history_size)  # Store 10 minutes of data (600 seconds)
        self.voltage_data = np.zeros((voltage_channels, pressure_history_size))  # Voltage for multiple channels
        self.flow_rate = np.zeros(pressure_history_size)  # Store 10 minutes of data (600 seconds)
        self.ps_current = np.zeros(pressure_history_size)  # Store 10 minutes of data (600 seconds)
        self.ps_voltage = np.zeros(pressure_history_size)
        self.running = True
    
    def update_pressure(self, pressure):
        """Update the pressure history with the new pressure value."""
        # Shift pressure history to the left (remove oldest data point)
        self.pressure_history = np.roll(self.pressure_history, -1)
        # Add new pressure reading to the end of the array
        self.pressure_history[-1] = pressure

    def update_voltages(self, voltages):
        """Update the voltage history for multiple channels."""
        self.voltage_data = np.roll(self.voltage_data, -1, axis=1)  # Shift all voltage histories
        self.voltage_data[:, -1] = voltages  # Update the latest voltages

    def update_flow_rate(self, flow_rate):
        """Update the flow rate history with the new flow rate value."""
        # Shift flow rate history to the left (remove oldest data point)
        self.flow_rate = np.roll(self.flow_rate, -1)
        # Add new flow rate reading to the end of the array
        self.flow_rate[-1] = flow_rate

    def update_ps_current(self, current):
        """Update the power supply current history with the new current value."""
        # Shift current history to the left (remove oldest data point)
        self.ps_current = np.roll(self.ps_current, -1)
        # Add new current reading to the end of the array
        self.ps_current[-1] = current
    
    def update_ps_voltage(self, voltage):
        """Update the power supply voltage history with the new voltage value."""
        # Shift voltage history to the left (remove oldest data point)
        self.ps_voltage = np.roll(self.ps_voltage, -1)
        # Add new voltage reading to the end of the array
        self.ps_voltage[-1] = voltage

    def run(self):
        while self.running:
            # Emit both pressure and voltage data as a dictionary
            data = {
                'pressure': self.pressure_history,
                'voltages': self.voltage_data,
                'flow_rate': self.flow_rate,
                'ps_current': self.ps_current,
                'ps_voltage': self.ps_voltage,
            }
            self.plot_update_signal.emit(data)  # Emit combined data

            # Sleep for a bit to mimic real-time data processing (adjust this as needed)
            self.msleep(5000)  # 5 seconds interval

    def stop(self):
        """Stop the thread when the application is closing."""
        self.running = False
        self.wait()
