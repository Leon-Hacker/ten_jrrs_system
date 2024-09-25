import sys
from PySide2.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                               QSlider, QLabel, QComboBox, QHBoxLayout)
from PySide2.QtCore import Qt, QTimer
from servo_control import ServoControl
from scservo_sdk import *  # Import SCServo SDK library

class ServoControlGUI(QWidget):
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
            self.servos[scs_id] = ServoControl(scs_id, self.portHandler, self.packetHandler,
                                               min_pos=2047, max_pos=3071)  # Updated min and max positions

        self.current_servo_id = 1  # Default servo ID
        self.current_servo = self.servos[self.current_servo_id]

        # Initialize the UI
        self.init_ui()

        # Timer to periodically update servo data
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_servo_data)
        self.timer.start(500)  # Update every 500ms

    def init_ui(self):
        self.setWindowTitle('Servo Control with Open/Close States')
        self.setGeometry(300, 300, 400, 250)

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

        self.setLayout(layout)

    def change_servo(self):
        """Change the current servo based on selection."""
        self.current_servo_id = self.servo_selector.currentData()
        self.current_servo = self.servos[self.current_servo_id]
        # Optionally, update the slider and button states to reflect the current servo
        self.update_servo_data()

    def toggle_servo_position(self):
        """Toggle between open (2047) and close (3071) positions."""
        if self.switch_button.isChecked():
            # If the button is checked, it's in the "Close" state
            self.switch_button.setText("Close")
            self.set_position(3071)  # Move to close position (270 degrees)
        else:
            # If the button is not checked, it's in the "Open" state
            self.switch_button.setText("Open")
            self.set_position(2047)  # Move to open position (180 degrees)

    def set_position(self, position):
        self.position_slider.setValue(position)
        try:
            self.current_servo.write_position(position)
        except Exception as e:
            self.info_label.setText(f"Error: {str(e)}")

    def slider_moved(self):
        position = self.position_slider.value()
        try:
            self.current_servo.write_position(position)
        except Exception as e:
            self.info_label.setText(f"Error: {str(e)}")

    def update_servo_data(self):
        try:
            pos, speed = self.current_servo.read_position_and_speed()
            self.info_label.setText(f"Servo {self.current_servo_id} - Position: {pos}, Speed: {speed}")
            # Update the slider and switch button to reflect the current servo's position
            self.position_slider.blockSignals(True)  # Prevent triggering slider_moved()
            self.position_slider.setValue(pos)
            self.position_slider.blockSignals(False)

            # Update switch button state
            if pos >= 3040:
                self.switch_button.blockSignals(True)
                self.switch_button.setChecked(True)
                self.switch_button.setText("Close")
                self.switch_button.blockSignals(False)
            elif pos <= 2080:
                self.switch_button.blockSignals(True)
                self.switch_button.setChecked(False)
                self.switch_button.setText("Open")
                self.switch_button.blockSignals(False)
            else:
                # If the servo is in an intermediate position
                self.switch_button.blockSignals(True)
                self.switch_button.setChecked(False)
                self.switch_button.setText("Adjusting")
                self.switch_button.blockSignals(False)

        except Exception as e:
            self.info_label.setText(f"Error: {str(e)}")

    def closeEvent(self, event):
        """Ensure the port is closed when the GUI is closed."""
        self.portHandler.closePort()
        event.accept()

# Main program
if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = ServoControlGUI()
    gui.show()
    sys.exit(app.exec_())