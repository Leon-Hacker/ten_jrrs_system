import sys
import numpy as np
import pyqtgraph as pg  # Added for real-time plotting
from pyqtgraph.widgets.RemoteGraphicsView import RemoteGraphicsView
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, QSlider, QLabel, QComboBox, QGridLayout, QFrame, QCheckBox, QHBoxLayout)
from PySide6.QtCore import Qt, QTimer
from servo_control import ServoControl, ServoThread
from voltage_collector import VoltageCollector, VoltageCollectorThread
from leakage_sensor import LeakageSensor, LeakageSensorThread
from pressure_sensor import PressureSensor, PressureSensorThread
from relay_control import RelayControl, RelayControlThread
from scservo_sdk import *  # Import SCServo SDK library
import datetime

class MainGUI(QWidget):
    def __init__(self):
        super().__init__()

        # Initialize shared port and packet handlers
        try:
            self.portHandler = PortHandler('COM12')  # Replace with your COM port
            self.packetHandler = sms_sts(self.portHandler)
            if not self.portHandler.openPort():
                raise Exception("Failed to open the port")
            if not self.portHandler.setBaudRate(38400):
                raise Exception("Failed to set the baudrate")
        except Exception as e:
            print(f"Error initializing port: {str(e)}")
            sys.exit(1)  # Exit if initialization fails

        # Initialize ServoControl instances for servos with IDs from 1 to 10
        self.servos = {}
        for scs_id in range(1, 11):
            self.servos[scs_id] = ServoControl(scs_id, self.portHandler, self.packetHandler, min_pos=2030, max_pos=3100)

        self.current_servo_id = 1  # Default servo ID set to 1
        self.current_servo = self.servos[self.current_servo_id]

        # Initialize the servo thread
        self.servo_thread = ServoThread(self.servos)
        self.servo_thread.position_updated.connect(self.update_servo_info)
        self.servo_thread.start()

        # Initialize the voltage collector
        self.voltage_collector = VoltageCollector('COM5')
        self.voltage_thread = VoltageCollectorThread(self.voltage_collector)
        self.voltage_thread.voltages_updated.connect(self.update_voltages)
        self.voltage_thread.start()

        # Initialize the leakage sensor and thread
        self.leakage_sensor = LeakageSensor('COM14')
        self.leakage_sensor_thread = LeakageSensorThread(self.leakage_sensor)
        self.leakage_sensor_thread.leak_status_signal.connect(self.update_leak_status)
        self.leakage_sensor_thread.start()

        # Initialize the pressure sensor and thread
        self.pressure_sensor = PressureSensor('COM15', baudrate=9600, address=1)
        self.pressure_sensor_thread = PressureSensorThread(self.pressure_sensor)
        self.pressure_sensor_thread.pressure_updated.connect(self.update_pressure)
        self.pressure_sensor_thread.start()

        # Initialize the relay control and thread
        self.relay_control = RelayControl('COM16', baudrate=115200, address=0x01)
        self.relay_control.open_connection()
        self.relay_thread = RelayControlThread(self.relay_control)
        self.relay_thread.relay_state_updated.connect(self.update_relay_states)
        self.relay_thread.relay_control_response.connect(self.handle_relay_response)
        self.relay_thread.start()

        # Pressure and voltage plot related
        self.pressure_history = np.zeros(600)  # Store 10 minutes of data (600 seconds)
        self.time_history = np.linspace(-600, 0, 600)  # Time axis, representing the last 10 minutes
        self.voltage_histories = [np.zeros(600) for _ in range(10)]  # 10 channels of voltage data

        # Initialize the UI
        self.init_ui()

        # Timer for real-time curves' updates
        self.pressure_update_timer = QTimer()
        self.pressure_update_timer.timeout.connect(self.update_plots)
        self.pressure_update_timer.start(2000)  # Update the plot every 2 seconds.

    def init_ui(self):
        self.setWindowTitle('Control with Voltage, Leak, Pressure, and Relay Management')
        self.setGeometry(300, 300, 1200, 600)

        # Main layout (horizontal layout to split the window into two sections)
        main_layout = QHBoxLayout()

        # Left side layout for pressure and voltage display (both plots)
        display_layout = QVBoxLayout()

        # Label to display the pressure value
        self.pressure_label = QLabel("Pressure: --- MPa", self)
        display_layout.addWidget(self.pressure_label)

        # RemoteGraphicsView setup for the pressure and voltage plots
        self.remote_view = RemoteGraphicsView()
        self.remote_view.setWindowTitle("Inlet Pressure and Voltage Over Time")

        # Set up the pressure plot in the remote process
        self.remote_plot = self.remote_view.pg.PlotItem()
        self.remote_plot._setProxyOptions(deferGetattr=True)  # Optimize access
        self.remote_view.setCentralItem(self.remote_plot)

        # Set plot labels and y-axis range for pressure
        self.remote_plot.setLabel('left', 'Pressure (MPa)')
        self.remote_plot.setLabel('bottom', 'Time (s)')
        self.remote_plot.setYRange(0, 1)  # Set y-axis from 0 to 1 MPa
        self.remote_curve_pressure = self.remote_plot.plot()

        # Set up a secondary plot for the voltage display
        self.remote_plot_voltage = self.remote_view.pg.PlotItem()
        self.remote_plot_voltage._setProxyOptions(deferGetattr=True)  # Optimize access
        self.remote_plot_voltage.setLabel('left', 'Voltage (V)')
        self.remote_plot_voltage.setYRange(0, 10)  # Set y-axis from 0 to 10V
        self.remote_curves_voltage = [self.remote_plot_voltage.plot() for _ in range(10)]

        # Add the pressure and voltage plots to the layout
        display_layout.addWidget(self.remote_view)

        # Add voltage channel selection checkboxes
        self.voltage_checkboxes = []
        checkbox_layout = QGridLayout()
        for i in range(10):
            checkbox = QCheckBox(f"Channel {i+1}")
            checkbox.setChecked(True)  # By default, show all channels
            checkbox_layout.addWidget(checkbox, i // 5, i % 5)
            self.voltage_checkboxes.append(checkbox)

        display_layout.addLayout(checkbox_layout)

        # Add the pressure display (label + plot) to the left side of the main layout
        main_layout.addLayout(display_layout)

        # Right side layout for servo controls, leakage, voltage, relay controls
        control_layout = QVBoxLayout()

        # Servo controls layout
        servo_layout = QGridLayout()
        for scs_id in self.servos.keys():
            servo_control_widget = self.create_servo_control_widget(scs_id)
            servo_layout.addWidget(servo_control_widget, (scs_id - 1) // 2, (scs_id - 1) % 2)
        control_layout.addLayout(servo_layout)

        # Leak detection indicator
        self.leak_label = QLabel("Leak Status: ---", self)
        self.leak_indicator = QFrame(self)
        self.leak_indicator.setFixedSize(20, 20)
        self.leak_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
        control_layout.addWidget(self.leak_label)
        control_layout.addWidget(self.leak_indicator)

        # Grid layout to display the first 10 voltages
        self.voltage_labels = [QLabel(f"Voltage {i+1}: --- V") for i in range(10)]
        voltage_layout = QGridLayout()
        for i, label in enumerate(self.voltage_labels):
            voltage_layout.addWidget(label, i // 5, i % 5)
        control_layout.addLayout(voltage_layout)

        # Relay control checkboxes
        self.relay_checkboxes = [QCheckBox(f"Channel {i+1}") for i in range(16)]
        relay_layout = QGridLayout()
        for i, checkbox in enumerate(self.relay_checkboxes):
            relay_layout.addWidget(checkbox, i // 4, i % 4)
        control_layout.addLayout(relay_layout)

        # Button to apply relay control
        self.apply_button = QPushButton("Apply Relay Control", self)
        self.apply_button.clicked.connect(self.apply_relay_control)
        control_layout.addWidget(self.apply_button)

        # Clearer relay status display using indicator frames
        self.relay_status_labels = [QLabel(f"Channel {i+1}: ---") for i in range(16)]
        self.relay_status_indicators = [QFrame(self) for _ in range(16)]

        relay_status_layout = QGridLayout()
        for i, (label, indicator) in enumerate(zip(self.relay_status_labels, self.relay_status_indicators)):
            indicator.setFixedSize(20, 20)
            indicator.setStyleSheet("background-color: grey; border-radius: 10px;")
            relay_status_layout.addWidget(label, i // 4, (i % 4) * 2)
            relay_status_layout.addWidget(indicator, i // 4, (i % 4) * 2 + 1)
        control_layout.addLayout(relay_status_layout)

        # Add the control layout to the main layout (right side)
        main_layout.addLayout(control_layout)

        # Set the main layout for the window
        self.setLayout(main_layout)

    def create_servo_control_widget(self, scs_id):
        """Create a widget for controlling a single servo."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Label to display the current servo position and speed
        info_label = QLabel(f"Servo {scs_id} Info: ", self)
        info_label.setObjectName(f"servo_info_{scs_id}")
        layout.addWidget(info_label)

        # Slider to control the servo position
        position_slider = QSlider(Qt.Horizontal, self)
        position_slider.setMinimum(2047)
        position_slider.setMaximum(3071)
        position_slider.setValue(2047)
        position_slider.setObjectName(f"servo_slider_{scs_id}")
        position_slider.valueChanged.connect(lambda value, sid=scs_id: self.slider_moved(sid, value))
        layout.addWidget(position_slider)

        # Switch button (Open/Close)
        switch_button = QPushButton('Open', self)
        switch_button.setCheckable(True)
        switch_button.setChecked(False)
        switch_button.setObjectName(f"servo_button_{scs_id}")
        switch_button.clicked.connect(lambda checked, sid=scs_id: self.toggle_servo_position(sid, checked))
        layout.addWidget(switch_button)

        widget.setLayout(layout)
        return widget

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
        self.pressure_label.setText(f"Inlet pressure of reactor: {pressure:.3f} MPa")

        # Shift pressure history to the left (removing the oldest data point)
        self.pressure_history = np.roll(self.pressure_history, -1)
        # Add new pressure reading to the end of the array
        self.pressure_history[-1] = pressure

    def update_plots(self):
        """Update both the pressure and voltage plots every 2 seconds."""
        if not self.remote_view.isVisible():  # Check if the remote view is still visible
            self.pressure_update_timer.stop()  # Stop the timer if the remote view is closed
            return

        now = datetime.datetime.now().strftime('%H:%M:%S')
        self.remote_plot.setLabel('bottom', f'Time (seconds) - Now: {now}')

        # Update the pressure plot
        try:
            self.remote_curve_pressure.setData(self.time_history, self.pressure_history, _callSync='off')
        except pg.multiprocess.remoteproxy.ClosedError:
            print("Remote process closed. Stopping updates.")
            self.pressure_update_timer.stop()
            return

        # Update the voltage plot based on selected channels
        selected_channels = [i for i, checkbox in enumerate(self.voltage_checkboxes) if checkbox.isChecked()]
        for i, curve in enumerate(self.remote_curves_voltage):
            if i in selected_channels:
                curve.setData(self.time_history, self.voltage_histories[i], _callSync='off')
            else:
                curve.setData([], [])  # Hide unselected channels

    def update_voltages(self, voltages):
        """Update the voltage history and labels."""
        for i, voltage in enumerate(voltages[:10]):
            self.voltage_labels[i].setText(f"Voltage {i+1}: {voltage:.2f} V")
            self.voltage_histories[i] = np.roll(self.voltage_histories[i], -1)
            self.voltage_histories[i][-1] = voltage

    def toggle_servo_position(self, servo_id, checked):
        position = 3071 if checked else 2047
        self.servo_thread.write_position_signal.emit(servo_id, position)

    def slider_moved(self, servo_id, position):
        self.servo_thread.write_position_signal.emit(servo_id, position)

    def update_servo_info(self, servo_id, pos, speed, temp):
        # Update the specific servo's info label and slider
        info_label = self.findChild(QLabel, f"servo_info_{servo_id}")
        position_slider = self.findChild(QSlider, f"servo_slider_{servo_id}")
        switch_button = self.findChild(QPushButton, f"servo_button_{servo_id}")

        if info_label and position_slider and switch_button:
            info_label.setText(f"Servo {servo_id} - Position: {pos}, Speed: {speed}, Temperature: {temp} ℃")
            position_slider.blockSignals(True)
            position_slider.setValue(pos)
            position_slider.blockSignals(False)

            if pos >= 3040:
                switch_button.blockSignals(True)
                switch_button.setChecked(True)
                switch_button.setText("Close")
                switch_button.blockSignals(False)
            elif pos <= 2100:
                switch_button.blockSignals(True)
                switch_button.setChecked(False)
                switch_button.setText("Open")
                switch_button.blockSignals(False)
            else:
                switch_button.blockSignals(True)
                switch_button.setChecked(True)
                switch_button.setText("Adjusting")
                switch_button.blockSignals(False)

    def update_relay_states(self, states):
        """Update the relay states with clear status labels and indicators."""
        for i, state in enumerate(states):
            self.relay_status_labels[i].setText(f"Channel {i+1}: {'ON' if state else 'OFF'}")
            color = "green" if state else "red"
            self.relay_status_indicators[i].setStyleSheet(f"background-color: {color}; border-radius: 10px;")

    def handle_relay_response(self, response):
        print(f"Relay control response: {response}")

    def closeEvent(self, event):
        """Gracefully close the application and stop all threads and processes."""
        # Stop the update timer to prevent further updates
        self.pressure_update_timer.stop()

        # Close the remote graphics view
        self.remote_view.close()

        # Stop and close all threads
        self.servo_thread.stop()
        self.voltage_thread.stop()
        self.leakage_sensor_thread.stop()
        self.pressure_sensor_thread.stop()
        self.relay_thread.stop()

        # Close the port and connections
        self.portHandler.closePort()
        self.voltage_collector.close_connection()
        self.leakage_sensor.close_connection()
        self.pressure_sensor.close_connection()
        self.relay_control.close_connection()

        event.accept()  # Proceed with the window close event


# Main program
if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = MainGUI()
    gui.show()
    sys.exit(app.exec())
