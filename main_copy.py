import sys
import numpy as np
import pyqtgraph as pg  # Added for real-time plotting
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, QSlider, QLabel, QComboBox, QGridLayout, QFrame, QCheckBox, QHBoxLayout, QSpinBox)
from PySide6.QtCore import Qt, QTimer
from servo_control import ServoControl, ServoThread
from voltage_collector import VoltageCollector, VoltageCollectorThread
from leakage_sensor import LeakageSensor, LeakageSensorThread
from pressure_sensor import PressureSensor, PressureSensorThread
from relay_control import RelayControl, RelayControlThread
from pump_control import PumpControl, PumpControlThread
from scservo_sdk import *  # Import SCServo SDK library
from data_update import DataUpdateThread
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

        # Initialize the leakage sensor and thread
        self.leakage_sensor = LeakageSensor('COM14')
        self.leakage_sensor_thread = LeakageSensorThread(self.leakage_sensor)
        self.leakage_sensor_thread.leak_status_signal.connect(self.update_leak_status)
        self.leakage_sensor_thread.start()

        # Initialize the pressure sensor and thread
        self.pressure_sensor = PressureSensor('COM15', baudrate=9600, address=1)
        self.pressure_sensor_thread = PressureSensorThread(self.pressure_sensor)
        self.pressure_sensor_thread.pressure_updated.connect(self.update_pressure)
        
        # Initialize the relay control and thread
        self.relay_control = RelayControl('COM16', baudrate=115200, address=0x01)
        self.relay_control.open_connection()
        self.relay_thread = RelayControlThread(self.relay_control)
        self.relay_thread.relay_state_updated.connect(self.update_relay_states)
        self.relay_thread.relay_control_response.connect(self.handle_relay_response)
        self.relay_thread.start()

        # Initialize the pump control and thread
        self.pump_control = PumpControl('COM13', baudrate=9600, address=1)
        self.pump_control.open_connection()
        self.pump_thread = PumpControlThread(self.pump_control)
        self.pump_thread.pressure_updated.connect(self.update_pump_pressure)
        self.pump_thread.flow_updated.connect(self.update_pump_flow)
        self.pump_thread.stroke_updated.connect(self.update_pump_stroke)
        self.pump_thread.status_updated.connect(self.update_pump_status)

        # Initialize pressure history and time history
        self.time_history = np.linspace(-600, 0, 600)  # Time axis, representing the last 10 minutes
        self.pressure_history = np.zeros(600) 
        self.voltage_channels = 10  # Number of voltage channels
        self.voltage_data = np.zeros((self.voltage_channels, 600))  # Voltage data history
        self.flow_data = np.zeros(600)  # Flow rate data history

        # Initialize the date updating thread
        self.data_updater = DataUpdateThread(pressure_history_size=600, voltage_channels=self.voltage_channels)
        self.pressure_sensor_thread.pressure_updated.connect(self.data_updater.update_pressure)
        self.voltage_thread.voltages_updated.connect(self.data_updater.update_voltages)
        self.pump_thread.flow_updated.connect(self.data_updater.update_flow_rate)
        self.data_updater.plot_update_signal.connect(self.update_plots)

        self.data_updater.start()
        self.pressure_sensor_thread.start()
        self.voltage_thread.start()
        self.pump_thread.start()

        # Initialize the UI
        self.init_ui()

        

    def init_ui(self):
        self.setWindowTitle('Control with Voltage, Leak, Pressure, and Relay Management')
        self.setGeometry(300, 300, 1200, 800)

        # Main layout (horizontal layout to split the window into two sections)
        main_layout = QHBoxLayout()

        # Display the pump control panel on the far left
        pump_layout = QVBoxLayout()
        # Pump control panel
        pump_control_panel = QVBoxLayout()

        # Pump state, outlet pressure, and stroke display in the same line
        pump_info_layout = QHBoxLayout()
        
        self.pump_state_label = QLabel("Pump State: ---", self)
        pump_info_layout.addWidget(self.pump_state_label)
        
        self.pump_pressure_label = QLabel("Pump Outlet Pressure: --- Bar", self)
        pump_info_layout.addWidget(self.pump_pressure_label)
        
        self.pump_stroke_label = QLabel("Pump Stroke: --- %", self)
        pump_info_layout.addWidget(self.pump_stroke_label)
        
        pump_control_panel.addLayout(pump_info_layout)

        # Start pump button
        self.start_pump_button = QPushButton("Start Pump", self)
        self.start_pump_button.clicked.connect(self.pump_thread.start_pump)
        pump_control_panel.addWidget(self.start_pump_button)

        # Stop pump button
        self.stop_pump_button = QPushButton("Stop Pump", self)
        self.stop_pump_button.clicked.connect(self.pump_thread.stop_pump)
        pump_control_panel.addWidget(self.stop_pump_button)
        
        # Set pump stroke (range: 0-100) - QSpinBox and button
        stroke_layout = QHBoxLayout()
        self.stroke_spinbox = QSpinBox(self)
        self.stroke_spinbox.setRange(0, 100)
        self.stroke_spinbox.setValue(0)
        stroke_layout.addWidget(QLabel("Set Pump Stroke (%):", self))
        stroke_layout.addWidget(self.stroke_spinbox)

        self.set_stroke_button = QPushButton("Set Stroke", self)
        self.set_stroke_button.clicked.connect(self.set_pump_stroke)
        stroke_layout.addWidget(self.set_stroke_button)

        pump_control_panel.addLayout(stroke_layout)


        # Pump flow rate display
        self.pump_flow_label = QLabel("Pump Flow Rate: --- L/h", self)
        pump_control_panel.addWidget(self.pump_flow_label)

        # Pump flow rate real time plot set up
        self.pump_flow_plot_widget = pg.PlotWidget(title="Pump Flow Rate Over Time")
        self.pump_flow_plot_widget.setLabel('left', 'Flow Rate (L/h)')
        self.pump_flow_plot_widget.setLabel('bottom', 'Time (s)')
        self.pump_flow_plot_widget.setYRange(0, 400)  # Adjust the y-axis range as needed
        self.pump_flow_curve = self.pump_flow_plot_widget.plot(self.time_history, self.flow_data, pen='b')

        pump_control_panel.addWidget(self.pump_flow_plot_widget)

        # Add pump control panel to the main layout
        pump_layout.addLayout(pump_control_panel)
        main_layout.addLayout(pump_layout)

        # Left side layout for pressure display (both label and plot)
        display_layout = QVBoxLayout()

        # Label to display the pressure value
        self.pressure_label = QLabel("Pressure: --- MPa", self)
        display_layout.addWidget(self.pressure_label)

        # Pressure plot setup
        self.pressure_plot_widget = pg.PlotWidget(title="Inlet Pressure Over Time")
        self.pressure_plot_widget.setLabel('left', 'Pressure (MPa)')
        self.pressure_plot_widget.setLabel('bottom', 'Time (s)')
        self.pressure_plot_widget.setYRange(0, 1)  # Set y-axis from 0 to 1 MPa
        self.pressure_curve = self.pressure_plot_widget.plot(self.time_history, self.pressure_history, pen='y')

        display_layout.addWidget(self.pressure_plot_widget)

        # Voltage channel checkboxes to toggle channels
        self.voltage_checkboxes = []
        voltage_checkbox_layout = QGridLayout()
        for i in range(self.voltage_channels):
            checkbox = QCheckBox(f"Channel {i+1}")
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self.toggle_voltage_curve)
            self.voltage_checkboxes.append(checkbox)
            voltage_checkbox_layout.addWidget(checkbox, i // 5, i % 5)
        display_layout.addLayout(voltage_checkbox_layout)

        # Grid layout to display the first 10 voltages - placed before the voltage curve
        self.voltage_labels = [QLabel(f"Voltage {i+1}: --- V") for i in range(10)]
        voltage_label_layout = QGridLayout()
        for i, label in enumerate(self.voltage_labels):
            voltage_label_layout.addWidget(label, i // 5, i % 5)
        display_layout.addLayout(voltage_label_layout)

        # Voltage plot setup (new) with legend
        self.voltage_plot_widget = pg.PlotWidget(title="Voltage Channels Over Time")
        self.voltage_plot_widget.setLabel('left', 'Voltage (V)')
        self.voltage_plot_widget.setLabel('bottom', 'Time (s)')

        # Add the legend to the voltage plot
        self.voltage_plot_widget.addLegend(offset=(10, 10))

        self.voltage_curves = []
        for i in range(self.voltage_channels):  # Assuming voltage_channels = 10
            curve = self.voltage_plot_widget.plot(self.time_history, self.voltage_data[i], pen=(i, self.voltage_channels), name=f"Channel {i+1}")
            self.voltage_curves.append(curve)

        # Add voltage plot under the checkboxes and labels
        display_layout.addWidget(self.voltage_plot_widget)

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

    def update_plots(self, data):
        """Update both the pressure and voltage plots."""
        pressure_history = data['pressure']
        voltage_data = data['voltages']
        flow_history = data['flow_rate']

        # Update the pressure plot
        
        self.pressure_curve.setData(self.time_history, pressure_history)

        # Update the voltage plot with selected channels
        for i, curve in enumerate(self.voltage_curves):
            if self.voltage_checkboxes[i].isChecked():
                curve.setData(self.time_history, voltage_data[i])
            else:
                curve.setData([], [])  # Hide the curve if checkbox is unchecked

        # Update the pump flow rate plot
        self.pump_flow_curve.setData(self.time_history, flow_history)
        now = datetime.datetime.now().strftime('%H:%M:%S')
        self.pump_flow_plot_widget.setLabel('bottom', f'Time (seconds) - Now: {now}')

    def toggle_voltage_curve(self):
        """Update the voltage plot when channel selection changes."""
        self.update_plots({'pressure': self.pressure_history, 'voltages': self.voltage_data})

    def update_voltages(self, voltages):
        for i, voltage in enumerate(voltages[:10]):
            self.voltage_labels[i].setText(f"Voltage {i+1}: {voltage:.2f} V")

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

    def update_pump_pressure(self, pressure):
        self.pump_pressure_label.setText(f"Pump Outlet Pressure: {pressure:.3f} Bar")
    
    def update_pump_flow(self, flow):
        self.pump_flow_label.setText(f"Pump Flow Rate: {flow:.3f} L/h")

    def update_pump_stroke(self, stroke):
        self.pump_stroke_label.setText(f"Pump Stroke: {stroke:.3f} %")
    
    def update_pump_status(self, status):
        self.pump_state_label.setText(f"Pump State: {status}")

    def set_pump_stroke(self):
        stroke = self.stroke_spinbox.value()
        self.pump_thread.set_stroke(stroke)

    def closeEvent(self, event):
        self.pump_thread.stop()
        self.servo_thread.stop()
        self.voltage_thread.stop()
        self.leakage_sensor_thread.stop()
        self.pressure_sensor_thread.stop()
        self.relay_thread.stop()
        self.data_updater.stop()
        self.portHandler.closePort()
        self.pump_control.close_connection()
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
    sys.exit(app.exec())
