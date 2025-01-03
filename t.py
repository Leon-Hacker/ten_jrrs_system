import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLabel, QPushButton, QLineEdit, QHBoxLayout, QMessageBox
)
from PySide6.QtCore import QThread

# 1. Import your GearPumpController and GearpumpControlWorker
from gearpump_control import GearPumpController, GearpumpControlWorker

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gear Pump Control Test")
        
        # ---------------------------
        #  Setup UI Elements
        # ---------------------------
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Labels to show read values
        self.flow_label = QLabel("Flow: - mL/min")
        self.rotate_label = QLabel("Rotate: - R/min")
        self.pressure_label = QLabel("Pressure: - bar")
        self.temperature_label = QLabel("Temperature: - °C")
        self.pump_state_label = QLabel("Pump State: Unknown")

        # Add them to the layout
        main_layout.addWidget(self.flow_label)
        main_layout.addWidget(self.rotate_label)
        main_layout.addWidget(self.pressure_label)
        main_layout.addWidget(self.temperature_label)
        main_layout.addWidget(self.pump_state_label)

        # Controls to set flow rate
        flow_layout = QHBoxLayout()
        self.flow_input = QLineEdit()
        self.flow_input.setPlaceholderText("Flow (mL/min)")
        self.flow_button = QPushButton("Set Flow")
        flow_layout.addWidget(self.flow_input)
        flow_layout.addWidget(self.flow_button)
        main_layout.addLayout(flow_layout)

        # Controls to set rotate rate
        rotate_layout = QHBoxLayout()
        self.rotate_input = QLineEdit()
        self.rotate_input.setPlaceholderText("Rotate (0-65535)")
        self.rotate_button = QPushButton("Set Rotate")
        rotate_layout.addWidget(self.rotate_input)
        rotate_layout.addWidget(self.rotate_button)
        main_layout.addLayout(rotate_layout)

        # Controls to set pump state
        pump_layout = QHBoxLayout()
        self.pump_state_input = QLineEdit()
        self.pump_state_input.setPlaceholderText("Pump State (0/1)")
        self.pump_state_button = QPushButton("Set Pump State")
        pump_layout.addWidget(self.pump_state_input)
        pump_layout.addWidget(self.pump_state_button)
        main_layout.addLayout(pump_layout)

        # Start/Stop monitoring
        self.start_button = QPushButton("Start Monitoring")
        self.stop_button = QPushButton("Stop Monitoring")
        main_layout.addWidget(self.start_button)
        main_layout.addWidget(self.stop_button)

        # ---------------------------
        #  Create Pump Controller
        # ---------------------------
        # Adjust port, baudrate, etc. as needed
        self.gearpump_controller = GearPumpController(port='COM20', baudrate=9600, timeout=1, slave_id=1)
        
        # Open the serial connection explicitly
        try:
            self.gearpump_controller._open_serial()
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", f"Failed to open serial connection: {e}")
            sys.exit(1)

        # ---------------------------
        #  Create Worker + Thread
        # ---------------------------
        self.worker_thread = QThread()
        self.worker = GearpumpControlWorker(gearpump_control=self.gearpump_controller)
        self.worker.moveToThread(self.worker_thread)

        # Connect signals: from thread started => worker.start_monitoring
        self.worker_thread.started.connect(self.worker.start_monitoring)
        self.worker_thread.finished.connect(self.worker.stop)

        # Connect custom signals from worker to update UI
        self.worker.flow_rate_updated.connect(self.update_flow_label)
        self.worker.rotate_rate_updated.connect(self.update_rotate_label)
        self.worker.pressure_updated.connect(self.update_pressure_label)
        self.worker.temperature_updated.connect(self.update_temperature_label)
        self.worker.pump_state_updated.connect(self.update_pump_state_label)

        # Connect signals for set_xxx operations
        self.worker.flow_rate_set_response.connect(self.on_flow_rate_set_response)
        self.worker.rotate_rate_set_response.connect(self.on_rotate_rate_set_response)
        self.worker.pump_state_set_response.connect(self.on_pump_state_set_response)

        # Connect UI button signals
        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button.clicked.connect(self.stop_monitoring)
        self.flow_button.clicked.connect(self.set_flow_rate)
        self.rotate_button.clicked.connect(self.set_rotate_rate)
        self.pump_state_button.clicked.connect(self.set_pump_state)

        # Start the worker thread immediately if desired
        # Uncomment the following lines to start monitoring on launch
        # self.start_button.click()

    # ----------------------------
    #    Start/Stop Monitoring
    # ----------------------------
    def start_monitoring(self):
        """Start the background thread that monitors the gear pump."""
        if not self.worker_thread.isRunning():
            self.worker_thread.start()
            QMessageBox.information(self, "Monitoring", "Started monitoring the gear pump.")
        else:
            QMessageBox.warning(self, "Monitoring", "Monitoring is already running.")

    def stop_monitoring(self):
        """Stop the monitoring and quit the thread."""
        if self.worker_thread.isRunning():
            self.worker.stop()
            self.worker_thread.quit()
            self.worker_thread.wait()
            QMessageBox.information(self, "Monitoring", "Stopped monitoring the gear pump.")
        else:
            QMessageBox.warning(self, "Monitoring", "Monitoring is not running.")

    # ----------------------------
    #    Worker => UI Updates
    # ----------------------------
    def update_flow_label(self, value: int):
        self.flow_label.setText(f"Flow: {value} mL/min")

    def update_rotate_label(self, value: int):
        self.rotate_label.setText(f"Rotate: {value} R/min")

    def update_pressure_label(self, value: float):
        self.pressure_label.setText(f"Pressure: {value:.2f} bar")

    def update_temperature_label(self, value: float):
        self.temperature_label.setText(f"Temperature: {value:.2f} °C")

    def update_pump_state_label(self, state: str):
        self.pump_state_label.setText(f"Pump State: {state}")

    # ----------------------------
    #    UI => Worker Commands
    # ----------------------------
    def set_flow_rate(self):
        """User clicked Set Flow. Parse input and call worker."""
        try:
            flow_val = int(self.flow_input.text())
            if flow_val < 0 or flow_val > 6553:  # Assuming flow_rate*10 fits in 0-65535
                QMessageBox.warning(self, "Input Error", "Flow rate must be between 0 and 6553 mL/min.")
                return
            self.worker.set_flow_rate(flow_val)  # Worker tries to set flow rate
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Invalid flow rate input. Please enter an integer.")

    def set_rotate_rate(self):
        """User clicked Set Rotate. Parse input and call worker."""
        try:
            rotate_val = int(self.rotate_input.text())
            if rotate_val < 0 or rotate_val > 65535:
                QMessageBox.warning(self, "Input Error", "Rotate rate must be between 0 and 65535 R/min.")
                return
            self.worker.set_rotate_rate(rotate_val)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Invalid rotate rate input. Please enter an integer.")

    def set_pump_state(self):
        """User clicked Set Pump State. Parse input and call worker."""
        try:
            state_val = int(self.pump_state_input.text())
            if state_val not in [0, 1]:
                QMessageBox.warning(self, "Input Error", "Pump state must be 0 (OFF) or 1 (ON).")
                return
            self.worker.set_pump_state(state_val)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Invalid pump state input. Please enter 0 or 1.")

    # ----------------------------
    #   Worker => UI Response
    # ----------------------------
    def on_flow_rate_set_response(self, success: bool):
        if success:
            QMessageBox.information(self, "Set Flow Rate", "Flow rate set successfully!")
        else:
            QMessageBox.critical(self, "Set Flow Rate", "Failed to set flow rate.")

    def on_rotate_rate_set_response(self, success: bool):
        if success:
            QMessageBox.information(self, "Set Rotate Rate", "Rotate rate set successfully!")
        else:
            QMessageBox.critical(self, "Set Rotate Rate", "Failed to set rotate rate.")

    def on_pump_state_set_response(self, success: bool):
        if success:
            QMessageBox.information(self, "Set Pump State", "Pump state set successfully!")
        else:
            QMessageBox.critical(self, "Set Pump State", "Failed to set pump state.")

    # ----------------------------
    #   Cleanup on Close
    # ----------------------------
    def closeEvent(self, event):
        # Stop monitoring if running
        self.stop_monitoring()
        
        # Close the serial connection
        try:
            self.gearpump_controller._close_serial()
        except Exception as e:
            QMessageBox.warning(self, "Close Connection", f"Failed to close serial connection: {e}")
        
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(500, 400)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
