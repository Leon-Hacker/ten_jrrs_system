import numpy as np
from PySide6.QtCore import QThread, Signal

class DataUpdateThread(QThread):
    plot_update_signal = Signal(dict)

    def __init__(self, pressure_history_size=600, voltage_channels=10, parent=None):
        super().__init__(parent)
        self.pressure_history = np.zeros(pressure_history_size)  # Store 10 minutes of data (600 seconds)
        self.voltage_data = np.zeros((voltage_channels, pressure_history_size))  # Voltage for multiple channels
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

    def run(self):
        while self.running:
            # Emit both pressure and voltage data as a dictionary
            data = {
                'pressure': self.pressure_history,
                'voltages': self.voltage_data
            }
            self.plot_update_signal.emit(data)  # Emit combined data

            # Sleep for a bit to mimic real-time data processing (adjust this as needed)
            self.msleep(5000)  # 5 seconds interval

    def stop(self):
        """Stop the thread when the application is closing."""
        self.running = False
        self.wait()
