import sys
from PySide2.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QSlider, QLabel, QHBoxLayout
from PySide2.QtCore import Qt, QTimer
from scservo_sdk import *  # Uses SCServo SDK library
import os

# Default settings (adjust as per your existing code)
SCS_ID = 1
BAUDRATE = 1000000
DEVICENAME = 'COM3'  # Replace with your device's COM port

SCS_MINIMUM_POSITION_VALUE = 1023
SCS_MAXIMUM_POSITION_VALUE = 2047
SCS_MOVING_SPEED = 40
SCS_MOVING_ACC = 10

# Initialize PortHandler and PacketHandler
portHandler = PortHandler(DEVICENAME)
packetHandler = sms_sts(portHandler)

# Open port and set baudrate
if not portHandler.openPort():
    print("Failed to open the port")
    sys.exit()

if not portHandler.setBaudRate(BAUDRATE):
    print("Failed to set baudrate")
    sys.exit()

# Function to write servo position
def write_servo_position(position):
    scs_comm_result, scs_error = packetHandler.WritePosEx(SCS_ID, position, SCS_MOVING_SPEED, SCS_MOVING_ACC)
    if scs_comm_result != COMM_SUCCESS:
        print(f"Communication Error: {packetHandler.getTxRxResult(scs_comm_result)}")
    elif scs_error != 0:
        print(f"Servo Error: {packetHandler.getRxPacketError(scs_error)}")

# Main GUI class
class ServoControlGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

        # Timer to periodically update servo data
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_servo_data)
        self.timer.start(500)  # Update every 500ms

    def init_ui(self):
        # Set window title and size
        self.setWindowTitle('Servo Control')
        self.setGeometry(300, 300, 400, 200)

        # Layout
        layout = QVBoxLayout()

        # Label to display the current servo position and speed
        self.info_label = QLabel("Servo Info: ", self)
        layout.addWidget(self.info_label)

        # Slider to control the servo position
        self.position_slider = QSlider(Qt.Horizontal, self)
        self.position_slider.setMinimum(SCS_MINIMUM_POSITION_VALUE)
        self.position_slider.setMaximum(SCS_MAXIMUM_POSITION_VALUE)
        self.position_slider.setValue((SCS_MAXIMUM_POSITION_VALUE - SCS_MINIMUM_POSITION_VALUE) // 2)
        self.position_slider.valueChanged.connect(self.slider_moved)
        layout.addWidget(self.position_slider)

        # Buttons for predefined positions (0, mid, max)
        button_layout = QHBoxLayout()

        self.btn_min = QPushButton('Min Position', self)
        self.btn_min.clicked.connect(lambda: self.set_position(SCS_MINIMUM_POSITION_VALUE))
        button_layout.addWidget(self.btn_min)

        self.btn_mid = QPushButton('Mid Position', self)
        self.btn_mid.clicked.connect(lambda: self.set_position((SCS_MAXIMUM_POSITION_VALUE + SCS_MINIMUM_POSITION_VALUE) // 2))
        button_layout.addWidget(self.btn_mid)

        self.btn_max = QPushButton('Max Position', self)
        self.btn_max.clicked.connect(lambda: self.set_position(SCS_MAXIMUM_POSITION_VALUE))
        button_layout.addWidget(self.btn_max)

        layout.addLayout(button_layout)

        # Set the layout
        self.setLayout(layout)

    def set_position(self, position):
        self.position_slider.setValue(position)
        write_servo_position(position)

    def slider_moved(self):
        # Called when the slider moves
        position = self.position_slider.value()
        write_servo_position(position)

    def update_servo_data(self):
        # Periodically read the current servo position and speed
        scs_present_position, scs_present_speed, scs_comm_result, scs_error = packetHandler.ReadPosSpeed(SCS_ID)
        if scs_comm_result == COMM_SUCCESS:
            self.info_label.setText(f"Servo Info - Position: {scs_present_position}, Speed: {scs_present_speed}")
        else:
            self.info_label.setText(f"Error: {packetHandler.getTxRxResult(scs_comm_result)}")

# Main function
if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = ServoControlGUI()
    gui.show()
    sys.exit(app.exec_())

    # Close the port when the application exits
    portHandler.closePort()
