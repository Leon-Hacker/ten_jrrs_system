import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

class DataUpdateThread(QThread):
    plot_update_signal = Signal(np.ndarray)

    def __init__(self, pressure_history_size=600, parent=None):
        super().__init__(parent)
        self.pressure_history = np.zeros(pressure_history_size)  # Store 10 minutes of data (600 seconds)
        self.running = True
    
    def update_pressure(self, pressure):
        """Update the pressure history with the new pressure value."""
        # Shift pressure history to the left (remove oldest data point)
        self.pressure_history = np.roll(self.pressure_history, -1)
        # Add new pressure reading to the end of the array
        self.pressure_history[-1] = pressure

    def run(self):
        while self.running:
            # Emit the updated data to be plotted in the main thread
            self.plot_update_signal.emit(self.pressure_history)

            # Sleep for a bit to mimic real-time data processing (adjust this as needed)
            self.msleep(5000)  # 5 seconds interval

    def stop(self):
        """Stop the thread when the application is closing."""
        self.running = False
        self.wait()
