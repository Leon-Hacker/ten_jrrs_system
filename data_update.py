import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, QTimer

class DataUpdateWorker(QObject):
    plot_update_signal = Signal(dict)
    stopped = Signal()

    def __init__(self, pressure_history_size=600, voltage_channels=10):
        super().__init__()
        self.pressure_history = np.zeros(pressure_history_size)  # Store 10 minutes of data (600 seconds)
        self.voltage_data = np.zeros((voltage_channels, pressure_history_size))  # Voltage for multiple channels
        self.flow_rate = np.zeros(pressure_history_size)  # Store 10 minutes of data (600 seconds)
        self.ps_current = np.zeros(pressure_history_size)  # Store 10 minutes of data (600 seconds)
        self.ps_voltage = np.zeros(pressure_history_size)
        self.running = True
        self.poll_timer = None

    def start(self):
        """Start the timer to begin emitting data updates."""
        self.poll_timer = QTimer()  # Timer for real-time data updates
        self.poll_timer.setInterval(5000)  # Set interval to 5 seconds
        self.poll_timer.timeout.connect(self.update_data)
        self.poll_timer.start()

    def stop(self):
        """Stop data updates when the application is closing."""
        self.running = False

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

    def update_ps_current(self, current):
        """Update the power supply current history with the new current value."""
        self.ps_current = np.roll(self.ps_current, -1)
        self.ps_current[-1] = current

    def update_ps_voltage(self, voltage):
        """Update the power supply voltage history with the new voltage value."""
        self.ps_voltage = np.roll(self.ps_voltage, -1)
        self.ps_voltage[-1] = voltage