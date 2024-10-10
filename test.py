import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QSlider, QPushButton, QGridLayout
from PySide6.QtCore import Qt
from servo_control import ServoControl, ServoThread
from scservo_sdk import *  # Import SCServo SDK library

class TestServoControlGUI(QWidget):
    def __init__(self):
        super().__init__()

        # Initialize shared port and packet handlers
        try:
            self.portHandler = PortHandler('COM12')  # Replace with your COM port
            self.packetHandler = sms_sts(self.portHandler)
            if not self.portHandler.openPort():
                raise Exception("Failed to open the port")
            if not self.portHandler.setBaudRate(115200):
                raise Exception("Failed to set the baudrate")
        except Exception as e:
            print(f"Error initializing port: {str(e)}")
            sys.exit(1)  # Exit if initialization fails

        # Initialize ServoControl instances for servos with IDs from 1 to 10
        self.servos = {}
        for scs_id in range(1, 11):
            self.servos[scs_id] = ServoControl(scs_id, self.portHandler, self.packetHandler, min_pos=2047, max_pos=3071)

        # Initialize the servo thread
        self.servo_thread = ServoThread(self.servos, self.packetHandler)
        self.servo_thread.position_updated.connect(self.update_servo_info)
        self.servo_thread.start()

        # Initialize the UI
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Servo Control Test')
        self.setGeometry(300, 300, 800, 600)

        layout = QVBoxLayout()

        # Servo controls layout
        self.servo_info_labels = {}
        self.servo_sliders = {}
        self.servo_buttons = {}
        servo_layout = QGridLayout()
        for scs_id in self.servos.keys():
            servo_control_widget = self.create_servo_control_widget(scs_id)
            servo_layout.addWidget(servo_control_widget, (scs_id - 1) // 2, (scs_id - 1) % 2)
        layout.addLayout(servo_layout)

        self.setLayout(layout)

    def create_servo_control_widget(self, scs_id):
        """Create a widget for controlling a single servo."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Label to display the current servo position and speed
        info_label = QLabel(f"Servo {scs_id} Info: ", self)
        info_label.setObjectName(f"servo_info_{scs_id}")
        layout.addWidget(info_label)
        self.servo_info_labels[scs_id] = info_label

        # Slider to control the servo position
        position_slider = QSlider(Qt.Horizontal, self)
        position_slider.setMinimum(2047)
        position_slider.setMaximum(3071)
        position_slider.setValue(2047)
        position_slider.setObjectName(f"servo_slider_{scs_id}")
        position_slider.valueChanged.connect(lambda value, sid=scs_id: self.slider_moved(sid, value))
        layout.addWidget(position_slider)
        self.servo_sliders[scs_id] = position_slider

        # Switch button (Open/Close)
        switch_button = QPushButton('Open', self)
        switch_button.setCheckable(True)
        switch_button.setChecked(False)
        switch_button.setObjectName(f"servo_button_{scs_id}")
        switch_button.clicked.connect(lambda checked, sid=scs_id: self.toggle_servo_position(sid, checked))
        layout.addWidget(switch_button)
        self.servo_buttons[scs_id] = switch_button

        widget.setLayout(layout)
        return widget

    def toggle_servo_position(self, servo_id, checked):
        position = 3071 if checked else 2047
        self.servo_thread.write_position_signal.emit(servo_id, position)

    def slider_moved(self, servo_id, position):
        self.servo_thread.write_position_signal.emit(servo_id, position)

    def update_servo_info(self, servo_id, pos, speed):
        # Update the specific servo's info label and slider
        info_label = self.servo_info_labels.get(servo_id)
        position_slider = self.servo_sliders.get(servo_id)
        switch_button = self.servo_buttons.get(servo_id)

        if info_label and position_slider and switch_button:
            info_label.setText(f"Servo {servo_id} - Position: {pos}, Speed: {speed}")
            position_slider.blockSignals(True)
            position_slider.setValue(pos)
            position_slider.blockSignals(False)

            if pos >= 3030:
                switch_button.blockSignals(True)
                switch_button.setChecked(True)
                switch_button.setText("Close")
                switch_button.blockSignals(False)
            elif pos <= 2090:
                switch_button.blockSignals(True)
                switch_button.setChecked(False)
                switch_button.setText("Open")
                switch_button.blockSignals(False)
            else:
                switch_button.blockSignals(True)
                switch_button.setChecked(True)
                switch_button.setText("Adjusting")
                switch_button.blockSignals(False)

    def closeEvent(self, event):
        self.servo_thread.stop()
        self.portHandler.closePort()
        event.accept()

# Main program
if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = TestServoControlGUI()
    gui.show()
    sys.exit(app.exec_())
