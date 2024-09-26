import sys
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, QSlider, QLabel, QComboBox, QGridLayout)
from PySide6.QtCore import Qt, QTimer
from servo_control import ServoControl, ServoThread
from voltage_collector import VoltageCollector, VoltageCollectorThread
from scservo_sdk import *  # Import SCServo SDK library


class MainGUI(QWidget):
    def __init__(self):
        super().__init__()

        # Initialize shared port and packet handlers
        try:
            self.portHandler = PortHandler('/dev/tty.usbserial-110')  # Replace with your COM port
            self.packetHandler = sms_sts(self.portHandler)
            if not self.portHandler.openPort():
                raise Exception("Failed to open the port")
            if not self.portHandler.setBaudRate(1000000):
                raise Exception("Failed to set the baudrate")
        except Exception as e:
            print(f"Error initializing port: {str(e)}")
            sys.exit(1)  # Exit if initialization fails

        # Create ServoControl instances for servos with IDs from 1 to 10
        self.servos = {}
        for scs_id in range(1, 11):
            self.servos[scs_id] = ServoControl(scs_id, self.portHandler, self.packetHandler, min_pos=2047, max_pos=3071)

        self.current_servo_id = 1  # Default servo ID set to 1
        self.current_servo = self.servos[self.current_servo_id]  # Set current_servo to the servo with ID 1

        # Initialize the servo thread
        self.servo_thread = ServoThread(self.servos)
        self.servo_thread.position_updated.connect(self.update_servo_info)  # Connect position update signal to slot
        self.servo_thread.start()

        # Initialize the voltage collector
        self.voltage_collector = VoltageCollector()

        # Initialize the voltage collector thread
        self.voltage_thread = VoltageCollectorThread(self.voltage_collector)
        self.voltage_thread.voltages_updated.connect(self.update_voltages)  # Connect to update voltage labels
        self.voltage_thread.start()

        # Initialize the UI
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Servo Control with Voltage Display')
        self.setGeometry(300, 300, 400, 350)

        layout = QVBoxLayout()

        # Servo selection dropdown
        self.servo_selector = QComboBox(self)
        for scs_id in self.servos.keys():
            self.servo_selector.addItem(f"Servo {scs_id}", scs_id)
        self.servo_selector.currentIndexChanged.connect(self.change_servo)
        layout.addWidget(QLabel("Select Servo:"))
        layout.addWidget(self.servo_selector)

        # Label to display the current servo position and speed
        self.info_label = QLabel("Servo Info: ", self)
        layout.addWidget(self.info_label)

        # Slider to control the servo position
        self.position_slider = QSlider(Qt.Horizontal, self)
        self.position_slider.setMinimum(2047)  # Set to 180 degrees (Open)
        self.position_slider.setMaximum(3071)  # Set to 270 degrees (Close)
        self.position_slider.setValue(2047)  # Default to Open (2047)
        self.position_slider.valueChanged.connect(self.slider_moved)
        layout.addWidget(self.position_slider)

        # Switch button (Open/Close)
        self.switch_button = QPushButton('Open', self)
        self.switch_button.setCheckable(True)
        self.switch_button.setChecked(False)  # Default is open
        self.switch_button.clicked.connect(self.toggle_servo_position)
        layout.addWidget(self.switch_button)

        # Grid layout to display the first 10 voltages
        self.voltage_labels = [QLabel(f"Voltage {i+1}: --- V") for i in range(10)]
        voltage_layout = QGridLayout()
        for i, label in enumerate(self.voltage_labels):
            voltage_layout.addWidget(label, i // 5, i % 5)  # Two rows, five columns
        layout.addLayout(voltage_layout)

        self.setLayout(layout)

    def change_servo(self):
        """Change the current servo based on selection."""
        self.current_servo_id = self.servo_selector.currentData()

    def toggle_servo_position(self):
        """Toggle between open (2047) and close (3071) positions."""
        position = 3071 if self.switch_button.isChecked() else 2047
        self.servo_thread.write_position_signal.emit(self.current_servo_id, position)  # Emit signal to worker thread

    def slider_moved(self):
        position = self.position_slider.value()
        self.servo_thread.write_position_signal.emit(self.current_servo_id, position)  # Emit signal to worker thread

    def update_servo_info(self, servo_id, pos, speed):
        """Update the UI with the current servo's position and speed."""
        if servo_id == self.current_servo_id:
            self.info_label.setText(f"Servo {self.current_servo_id} - Position: {pos}, Speed: {speed}")
            # Update the slider and switch button to reflect the current servo's position
            self.position_slider.blockSignals(True)  # Prevent triggering slider_moved()
            self.position_slider.setValue(pos)
            self.position_slider.blockSignals(False)

            # Update switch button state
            if pos >= 3030:
                self.switch_button.blockSignals(True)
                self.switch_button.setChecked(True)
                self.switch_button.setText("Close")
                self.switch_button.blockSignals(False)
            elif pos <= 2090:
                self.switch_button.blockSignals(True)
                self.switch_button.setChecked(False)
                self.switch_button.setText("Open")
                self.switch_button.blockSignals(False)
            else:
                # Adjusting state (position is between Open and Close)
                self.switch_button.blockSignals(True)
                self.switch_button.setChecked(True)  # Keep it unchecked since it’s not fully Open or Close
                self.switch_button.setText("Adjusting")
                self.switch_button.blockSignals(False)

    def update_voltages(self, voltages):
        """Update the voltage labels."""
        for i, voltage in enumerate(voltages[:10]):  # Only update the first 10 voltages
            self.voltage_labels[i].setText(f"Voltage {i+1}: {voltage:.2f} V")

    def closeEvent(self, event):
        """Ensure the port is closed when the GUI is closed."""
        self.servo_thread.stop()  # Stop the servo thread when the window is closed
        self.voltage_thread.stop()  # Stop the voltage collector thread
        self.portHandler.closePort()  # Close the servo communication port
        self.voltage_collector.close_connection()  # Close the voltage collector connection
        event.accept()

# Main program
if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = MainGUI()
    gui.show()
    sys.exit(app.exec_())