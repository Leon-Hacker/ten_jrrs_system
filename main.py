import sys
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, QSlider, QLabel, QComboBox, QGridLayout, QFrame, QCheckBox)
from PySide6.QtCore import Qt
from servo_control import ServoControl, ServoThread
from voltage_collector import VoltageCollector, VoltageCollectorThread
from leakage_sensor import LeakageSensor, LeakageSensorThread
from pressure_sensor import PressureSensor, PressureSensorThread
from relay_control import RelayControl, RelayControlThread
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

        # Initialize ServoControl instances for servos with IDs from 1 to 10
        self.servos = {}
        for scs_id in range(1, 11):
            self.servos[scs_id] = ServoControl(scs_id, self.portHandler, self.packetHandler, min_pos=2047, max_pos=3071)

        self.current_servo_id = 1  # Default servo ID set to 1
        self.current_servo = self.servos[self.current_servo_id]

        # Initialize the servo thread
        self.servo_thread = ServoThread(self.servos)
        self.servo_thread.position_updated.connect(self.update_servo_info)
        self.servo_thread.start()

        # Initialize the voltage collector
        self.voltage_collector = VoltageCollector()
        self.voltage_thread = VoltageCollectorThread(self.voltage_collector)
        self.voltage_thread.voltages_updated.connect(self.update_voltages)
        self.voltage_thread.start()

        # Initialize the leakage sensor and thread
        self.leakage_sensor = LeakageSensor('/dev/tty.usbserial-12440')
        self.leakage_sensor_thread = LeakageSensorThread(self.leakage_sensor)
        self.leakage_sensor_thread.leak_status_signal.connect(self.update_leak_status)
        self.leakage_sensor_thread.start()

        # Initialize the pressure sensor and thread
        self.pressure_sensor = PressureSensor('/dev/tty.usbserial-120', baudrate=9600, address=1)
        self.pressure_sensor_thread = PressureSensorThread(self.pressure_sensor)
        self.pressure_sensor_thread.pressure_updated.connect(self.update_pressure)
        self.pressure_sensor_thread.start()

        # Initialize the relay control and thread
        self.relay_control = RelayControl('/dev/tty.usbserial-130', baudrate=115200, address=0x01)
        self.relay_control.open_connection()
        self.relay_thread = RelayControlThread(self.relay_control)
        self.relay_thread.relay_state_updated.connect(self.update_relay_states)
        self.relay_thread.relay_control_response.connect(self.handle_relay_response)
        self.relay_thread.start()

        # Initialize the UI
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Control with Voltage, Leak, Pressure, and Relay Management')
        self.setGeometry(300, 300, 500, 600)

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
        self.position_slider.setMinimum(2047)
        self.position_slider.setMaximum(3071)
        self.position_slider.setValue(2047)
        self.position_slider.valueChanged.connect(self.slider_moved)
        layout.addWidget(self.position_slider)

        # Switch button (Open/Close)
        self.switch_button = QPushButton('Open', self)
        self.switch_button.setCheckable(True)
        self.switch_button.setChecked(False)
        self.switch_button.clicked.connect(self.toggle_servo_position)
        layout.addWidget(self.switch_button)

        # Leak detection indicator
        self.leak_label = QLabel("Leak Status: ---", self)
        self.leak_indicator = QFrame(self)
        self.leak_indicator.setFixedSize(20, 20)
        self.leak_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
        layout.addWidget(self.leak_label)
        layout.addWidget(self.leak_indicator)

        # Grid layout to display the first 10 voltages
        self.voltage_labels = [QLabel(f"Voltage {i+1}: --- V") for i in range(10)]
        voltage_layout = QGridLayout()
        for i, label in enumerate(self.voltage_labels):
            voltage_layout.addWidget(label, i // 5, i % 5)
        layout.addLayout(voltage_layout)

        # Label to display the pressure value
        self.pressure_label = QLabel("Pressure: --- MPa", self)
        layout.addWidget(self.pressure_label)

        # Relay control checkboxes
        self.relay_checkboxes = [QCheckBox(f"Channel {i+1}") for i in range(16)]
        relay_layout = QGridLayout()
        for i, checkbox in enumerate(self.relay_checkboxes):
            relay_layout.addWidget(checkbox, i // 4, i % 4)
        layout.addLayout(relay_layout)

        # Button to apply relay control
        self.apply_button = QPushButton("Apply Relay Control", self)
        self.apply_button.clicked.connect(self.apply_relay_control)
        layout.addWidget(self.apply_button)

        # Clearer relay status display using indicator frames
        self.relay_status_labels = [QLabel(f"Channel {i+1}: ---") for i in range(16)]
        self.relay_status_indicators = [QFrame(self) for _ in range(16)]

        relay_status_layout = QGridLayout()
        for i, (label, indicator) in enumerate(zip(self.relay_status_labels, self.relay_status_indicators)):
            indicator.setFixedSize(20, 20)
            indicator.setStyleSheet("background-color: grey; border-radius: 10px;")
            relay_status_layout.addWidget(label, i // 4, (i % 4) * 2)
            relay_status_layout.addWidget(indicator, i // 4, (i % 4) * 2 + 1)
        layout.addLayout(relay_status_layout)

        self.setLayout(layout)

    def apply_relay_control(self):
        """Apply the relay control based on the checkboxes."""
        channels = []
        states = []
        for i, checkbox in enumerate(self.relay_checkboxes):
            channels.append(i + 1)  # Channels are 1-based
            states.append(1 if checkbox.isChecked() else 0)  # 1 for ON, 0 for OFF

        self.relay_thread.control_relay(channels, states)

    def update_leak_status(self, leak_detected):
        if leak_detected:
            self.leak_label.setText("Leak Status: Leak Detected")
            self.leak_indicator.setStyleSheet("background-color: red; border-radius: 10px;")
        else:
            self.leak_label.setText("Leak Status: No Leak Detected")
            self.leak_indicator.setStyleSheet("background-color: green; border-radius: 10px;")

    def update_pressure(self, pressure):
        self.pressure_label.setText(f"Pressure: {pressure:.3f} MPa")

    def update_voltages(self, voltages):
        for i, voltage in enumerate(voltages[:10]):
            self.voltage_labels[i].setText(f"Voltage {i+1}: {voltage:.2f} V")

    def change_servo(self):
        self.current_servo_id = self.servo_selector.currentData()

    def toggle_servo_position(self):
        position = 3071 if self.switch_button.isChecked() else 2047
        self.servo_thread.write_position_signal.emit(self.current_servo_id, position)

    def slider_moved(self):
        position = self.position_slider.value()
        self.servo_thread.write_position_signal.emit(self.current_servo_id, position)

    def update_servo_info(self, servo_id, pos, speed):
        if servo_id == self.current_servo_id:
            self.info_label.setText(f"Servo {self.current_servo_id} - Position: {pos}, Speed: {speed}")
            self.position_slider.blockSignals(True)
            self.position_slider.setValue(pos)
            self.position_slider.blockSignals(False)

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
                self.switch_button.blockSignals(True)
                self.switch_button.setChecked(True)
                self.switch_button.setText("Adjusting")
                self.switch_button.blockSignals(False)

    def update_relay_states(self, states):
        """Update the relay states with clear status labels and indicators."""
        for i, state in enumerate(states):
            self.relay_status_labels[i].setText(f"Channel {i+1}: {'ON' if state else 'OFF'}")
            color = "green" if state else "red"
            self.relay_status_indicators[i].setStyleSheet(f"background-color: {color}; border-radius: 10px;")

    def handle_relay_response(self, response):
        print(f"Relay control response: {response}")

    def closeEvent(self, event):
        self.servo_thread.stop()
        self.voltage_thread.stop()
        self.leakage_sensor_thread.stop()
        self.pressure_sensor_thread.stop()
        self.relay_thread.stop()
        self.portHandler.closePort()
        self.voltage_collector.close_connection()
        self.leakage_sensor.close_connection()
        self.pressure_sensor.close_connection()
        self.relay_control.close_connection()
        event.accept()


# Main program
if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = MainGUI()
    gui.show()
    sys.exit(app.exec_())