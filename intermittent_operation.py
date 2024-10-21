import serial
import struct
import crcmod
import time
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker


class PumpControlThread(QThread):
    pressure_updated = Signal(float)  # Signal to update pressure in the GUI
    flow_updated = Signal(float)      # Signal to update flow in the GUI
    stroke_updated = Signal(float)    # Signal to update stroke in the GUI
    status_updated = Signal(str)      # Signal to update pump status in the GUI

    def __init__(self, pump_control, parent=None):
        """Initialize the PumpControlThread class."""
        super().__init__(parent)
        self.pump_control = pump_control
        self.running = True
        self.mutex = QMutex()  # Ensure thread-safe operation

    def run(self):
        """Continuously monitor pump parameters in the background."""
        while self.running:
            with QMutexLocker(self.mutex):
                try:
                    flow, pressure, stroke = self.pump_control.read_pump_parameters()
                    if pressure is not None:
                        self.pressure_updated.emit(pressure)
                    if flow is not None:
                        self.flow_updated.emit(flow)
                    else:
                        self.flow_updated.emit(-1)
                    if stroke is not None:
                        self.stroke_updated.emit(stroke)
                    self.msleep(50)
                    status = self.pump_control.read_pump_status()
                    if status is not None:
                        self.status_updated.emit(status)
                    self.msleep(50)
                except Exception as e:
                    print(f"Error reading pump parameters: {e}")
            self.msleep(900)  # Poll every second

    def set_stroke(self, stroke_value):
        """Set the stroke of the pump in a thread-safe manner."""
        with QMutexLocker(self.mutex):
            try:
                success = self.pump_control.set_stroke(stroke_value)
                if success:
                    print(f"Stroke set to {stroke_value}%")
                else:
                    print(f"Failed to set stroke to {stroke_value}%")
            except Exception as e:
                print(f"Error setting stroke: {e}")

    def start_pump(self):
        """Start the pump in a thread-safe manner."""
        with QMutexLocker(self.mutex):
            try:
                self.pump_control.start_pump()
            except Exception as e:
                print(f"Error starting pump: {e}")

    def stop_pump(self):
        """Stop the pump in a thread-safe manner."""
        with QMutexLocker(self.mutex):
            try:
                self.pump_control.stop_pump()
            except Exception as e:
                print(f"Error stopping pump: {e}")

    def pause_pump(self):
        """Pause the pump in a thread-safe manner."""
        with QMutexLocker(self.mutex):
            try:
                self.pump_control.pause_pump()
            except Exception as e:
                print(f"Error pausing pump: {e}")

    def stop(self):
        """Stop the thread."""
        self.running = False
        self.wait()