import os

os.environ['NUMEXPR_MAX_THREADS'] = '8'

import sys
import numpy as np
import pyqtgraph as pg  # Added for real-time plotting
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, QSlider, QLabel, QComboBox, QGridLayout, QFrame, QCheckBox, QHBoxLayout, QSpinBox, QDoubleSpinBox)
from PySide6.QtCore import Qt, QTimer, QThread
from servo_control import ServoControl, ServoWorker
from voltage_collector import VoltageCollector, VoltageCollectorWorker
from leakage_sensor import LeakageSensor, LeakageSensorThread
from pressure_sensor import PressureSensor, PressureSensorThread
from relay_control import RelayControl, RelayControlWorker
from gearpump_control import GearPumpController, GearpumpControlWorker
from power_supply import PowerSupplyControl, PowerSupplyWorker
from scservo_sdk import *  # Import SCServo SDK library
from data_update import DataUpdateWorker
import datetime
from inter_operv2 import InterOpWorker
from intermittent_dialog import IntermittentOperationDialog
from error_processing import ErrorProcessing

class MainGUI(QWidget):
    def __init__(self):
        super().__init__()

        # Initialize shared port and packet handlers
        try:
            self.portHandler = PortHandler('COM32')  # Replace with your COM port
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
        self.servo_control_worker = ServoWorker(self.servos)
        self.servo_thread = QThread()
        self.servo_control_worker.moveToThread(self.servo_thread)
        self.servo_thread.started.connect(self.servo_control_worker.start)
        self.servo_thread.finished.connect(self.servo_thread.deleteLater)
        self.servo_control_worker.servo_stopped.connect(self.servo_control_worker.stop)
        self.servo_control_worker.position_updated.connect(self.update_servo_info)
        self.servo_control_worker.button_checked_close.connect(self.servo_control_worker.write_position_checked_close)
        self.servo_control_worker.button_checked_open.connect(self.servo_control_worker.write_position_checked_open)
        self.servo_control_worker.button_checked_distorque_close.connect(self.servo_control_worker.disable_torque_checked_close)
        self.servo_control_worker.button_checked_distorque_open.connect(self.servo_control_worker.disable_torque_checked_open)

        # Initialize the voltage collector
        self.voltage_collector = VoltageCollector('COM7')
        self.voltage_collector_worker = VoltageCollectorWorker(self.voltage_collector)
        self.voltage_thread = QThread()
        self.voltage_collector_worker.moveToThread(self.voltage_thread)
        self.voltage_thread.started.connect(self.voltage_collector_worker.start_collecting)
        self.voltage_thread.finished.connect(self.voltage_thread.deleteLater)
        self.voltage_collector_worker.voltages_updated.connect(self.update_voltages)
        self.voltage_collector_worker.stopped.connect(self.voltage_collector_worker.stop_collecting)

        # Initialize the leakage sensor and thread
        self.leakage_sensor = LeakageSensor('COM5')
        self.leakage_sensor_thread = LeakageSensorThread(self.leakage_sensor)
        self.leakage_sensor_thread.leak_status_signal.connect(self.update_leak_status)
        self.leakage_sensor_thread.start()

        # Initialize the pressure sensor and thread
        self.pressure_sensor = PressureSensor('COM4', baudrate=9600, address=1)
        self.pressure_sensor_thread = PressureSensorThread(self.pressure_sensor)
        self.pressure_sensor_thread.pressure_updated.connect(self.update_pressure)
        
        # Initialize the relay control and thread
        self.relay_control = RelayControl('COM34', baudrate=115200, address=0x01)
        self.relay_control.open_connection()
        self.relay_control_worker = RelayControlWorker(self.relay_control)
        self.relay_control_thread = QThread()
        self.relay_control_worker.moveToThread(self.relay_control_thread)
        self.relay_control_thread.started.connect(self.relay_control_worker.start_monitoring)
        self.relay_control_thread.finished.connect(self.relay_control_thread.deleteLater)
        self.relay_control_worker.relay_state_updated.connect(self.update_relay_states)
        self.relay_control_worker.stopped.connect(self.relay_control_worker.stop)
        self.relay_control_worker.button_clicked.connect(self.relay_control_worker.control_relay)
        self.relay_control_worker.button_checked.connect(self.relay_control_worker.control_relay_checked)

        # Initialize the gear pump control and thread
        self.gearpump_control = GearPumpController(port='COM6', baudrate=9600, timeout=1, slave_id=1)
        self.gearpump_control.open_serial()
        self.gearpump_worker = GearpumpControlWorker(self.gearpump_control)
        self.gearpump_thread = QThread()
        self.gearpump_worker.moveToThread(self.gearpump_thread)
        self.gearpump_thread.started.connect(self.gearpump_worker.start_monitoring)
        self.gearpump_thread.finished.connect(self.gearpump_thread.deleteLater)
        self.gearpump_worker.pump_state_updated.connect(self.update_pump_state)
        self.gearpump_worker.pressure_updated.connect(self.update_pump_pressure)
        self.gearpump_worker.flow_rate_updated.connect(self.update_pump_flow_rate)
        self.gearpump_worker.rotate_rate_updated.connect(self.update_pump_rotate_rate)
        self.gearpump_worker.temperature_updated.connect(self.update_pump_temperature)
        self.gearpump_worker.pump_stopped.connect(self.gearpump_worker.stop)
        self.gearpump_worker.flow_rate_set.connect(self.gearpump_worker.set_flow_rate)
        self.gearpump_worker.rotate_rate_set.connect(self.gearpump_worker.set_rotate_rate)
        self.gearpump_worker.start_pump_set.connect(self.gearpump_worker.set_pump_state)
        self.gearpump_worker.stop_pump_set.connect(self.gearpump_worker.set_pump_state)
        self.gearpump_worker.button_checked.connect(self.gearpump_worker.set_rotate_rate_checked)

        # Initialize the power supply control and thread
        self.power_supply = PowerSupplyControl('COM17', baudrate=19200)
        self.power_supply.open_connection()
        self.power_supply_worker = PowerSupplyWorker(self.power_supply)
        self.power_supply_thread = QThread()
        self.power_supply_worker.moveToThread(self.power_supply_thread)
        self.power_supply_thread.started.connect(self.power_supply_worker.start_monitoring)
        self.power_supply_thread.finished.connect(self.power_supply_thread.deleteLater)
        self.power_supply_worker.power_state_updated.connect(self.update_ps_state)
        self.power_supply_worker.current_measured.connect(self.update_ps_current)
        self.power_supply_worker.voltage_measured.connect(self.update_ps_voltage)
        self.power_supply_worker.power_measured.connect(self.update_ps_power)
        self.power_supply_worker.ps_stopped.connect(self.power_supply_worker.stop)
        self.power_supply_worker.set_current_signal.connect(self.power_supply_worker.set_current)
        self.power_supply_worker.set_voltage_signal.connect(self.power_supply_worker.set_voltage)
        self.power_supply_worker.button_checked.connect(self.power_supply_worker.set_voltage_checked)

        # Initialize the intermittent operation worker and move it to a new thread
        self.io_worker = None  # Initialize without starting the worker yet
        self.io_worker_thread = None  # Initialize without starting the thread yet
        self.io_interval = 30  # Default interval minutes for intermittent operation

        # Initialize data history and time history
        self.time_history = np.linspace(-600, 0, 600)  # Time axis, representing the last 10 minutes
        self.pressure_history = np.zeros(600) 
        self.voltage_channels = 10  # Number of voltage channels
        self.voltage_data = np.zeros((self.voltage_channels, 600))  # Voltage data history
        self.flow_data = np.zeros(600)  # Flow rate data history
        self.ps_current = np.zeros(600)  # Power supply current history
        self.ps_voltage = np.zeros(600)  # Power supply voltage history

        # Initialize the date updating thread
        self.data_updater_thread = QThread()
        self.data_updater_worker = DataUpdateWorker(pressure_history_size=600, voltage_channels=self.voltage_channels)
        self.data_updater_worker.moveToThread(self.data_updater_thread)
        self.data_updater_worker.stopped.connect(self.data_updater_worker.stop)
        self.data_updater_thread.started.connect(self.data_updater_worker.start)
        self.data_updater_thread.finished.connect(self.data_updater_thread.deleteLater)
        self.pressure_sensor_thread.pressure_updated.connect(self.data_updater_worker.update_pressure)
        self.voltage_collector_worker.voltages_updated.connect(self.data_updater_worker.update_voltages)
        self.gearpump_worker.flow_rate_updated.connect(self.data_updater_worker.update_flow_rate)
        self.power_supply_worker.current_measured.connect(self.data_updater_worker.update_ps_current)
        self.power_supply_worker.voltage_measured.connect(self.data_updater_worker.update_ps_voltage)
        self.data_updater_worker.plot_update_signal.connect(self.update_plots)
        self.data_updater_worker.start_storing_signal.connect(self.data_updater_worker.start_storing_data)
        self.data_updater_worker.stop_storing_signal.connect(self.data_updater_worker.stop_storing_data)

        # Initialize the error processing worker and move it to a new thread
        self.error_processing_worker = ErrorProcessing()
        self.error_processing_thread = QThread()
        self.error_processing_worker.moveToThread(self.error_processing_thread)
        self.error_processing_thread.started.connect(self.error_processing_worker.start_checking)
        self.error_processing_thread.finished.connect(self.error_processing_thread.deleteLater)
        self.error_processing_worker.turn_off_ps.connect(self.power_supply_worker.turn_off_checked)
        self.error_processing_worker.turn_off_gp.connect(self.gearpump_worker.turnoff_pump_checked)
        self.gearpump_worker.pressure_updated.connect(self.error_processing_worker.get_gp_pressure)
        self.voltage_collector_worker.voltages_updated.connect(self.error_processing_worker.get_reacotr_voltages)
        self.error_processing_worker.stopped.connect(self.error_processing_worker.stop)

        self.data_updater_thread.start()
        self.pressure_sensor_thread.start()
        
        # Initialize the UI
        self.init_ui()
        
        self.voltage_thread.start()
        self.relay_control_thread.start()
        self.gearpump_thread.start()
        self.servo_thread.start()
        self.power_supply_thread.start()
        self.error_processing_thread.start()

    def init_ui(self):
        self.setWindowTitle('Control with Voltage, Leak, Pressure, and Relay Management')
        self.setGeometry(300, 300, 1200, 800)

        # Main layout (horizontal layout to split the window into two sections)
        main_layout = QHBoxLayout()

        # Display the gear pump control panel on the far left
        gearpump_layout = QVBoxLayout()
        # Gear pump control panel
        gearpump_control_panel = QVBoxLayout()

        # Gear Pump state, outlet pressure, temperature, flow rate and rotate rate display in the same line
        gearpump_info_layout = QHBoxLayout()
        
        self.gearpump_state_label = QLabel("Pump State: ---", self)
        gearpump_info_layout.addWidget(self.gearpump_state_label)
        
        self.gearpump_pressure_label = QLabel("P: --- Bar", self)
        gearpump_info_layout.addWidget(self.gearpump_pressure_label)
        
        self.gearpump_temperature_label = QLabel("T: --- °C", self)
        gearpump_info_layout.addWidget(self.gearpump_temperature_label)

        self.gearpump_flow_rate_label = QLabel("FR: --- mL/min", self)
        gearpump_info_layout.addWidget(self.gearpump_flow_rate_label)

        self.gearpump_rotate_rate_label = QLabel("RR: --- RPM", self)
        gearpump_info_layout.addWidget(self.gearpump_rotate_rate_label)
        
        gearpump_control_panel.addLayout(gearpump_info_layout)

        # Start pump button
        self.start_pump_button = QPushButton("Start Pump", self)
        self.start_pump_button.clicked.connect(self.start_gearpump)
        gearpump_control_panel.addWidget(self.start_pump_button)

        # Stop pump button
        self.stop_pump_button = QPushButton("Stop Pump", self)
        self.stop_pump_button.clicked.connect(self.stop_gearpump)
        gearpump_control_panel.addWidget(self.stop_pump_button)
        
        # Set pump rotate rate (range: 0-2700 rpm) - QSpinBox and button
        rotate_rate_layout = QHBoxLayout()
        self.rotate_rate_spinbox = QSpinBox(self)
        self.rotate_rate_spinbox.setRange(0, 3000)
        self.rotate_rate_spinbox.setValue(0)
        rotate_rate_layout.addWidget(QLabel("Set Rotate Rate (RPM):", self))
        rotate_rate_layout.addWidget(self.rotate_rate_spinbox)

        self.set_rotate_rate_button = QPushButton("Set Rotate Rate", self)
        self.set_rotate_rate_button.clicked.connect(self.set_gearpump_rotate_rate)
        rotate_rate_layout.addWidget(self.set_rotate_rate_button)

        gearpump_control_panel.addLayout(rotate_rate_layout)

        # Set pump flow rate (range: 0-6000 mL/min) - QSpinBox and button
        flow_rate_layout = QHBoxLayout()
        self.flow_rate_spinbox = QSpinBox(self)
        self.flow_rate_spinbox.setRange(0, 6000)
        self.flow_rate_spinbox.setValue(0)
        flow_rate_layout.addWidget(QLabel("Set Flow Rate (mL/min):", self))
        flow_rate_layout.addWidget(self.flow_rate_spinbox)

        self.set_flow_rate_button = QPushButton("Set Flow Rate", self)
        self.set_flow_rate_button.clicked.connect(self.set_gearpump_flow_rate)
        flow_rate_layout.addWidget(self.set_flow_rate_button)

        gearpump_control_panel.addLayout(flow_rate_layout)

        # Pump flow rate real time plot set up
        self.pump_flow_plot_widget = pg.PlotWidget(title="Pump Flow Rate Over Time")
        self.pump_flow_plot_widget.setLabel('left', 'Flow Rate (mL/min)')
        self.pump_flow_plot_widget.setLabel('bottom', 'Time (s)')
        self.pump_flow_plot_widget.setYRange(0, 6000)  # Adjust the y-axis range as needed
        self.pump_flow_curve = self.pump_flow_plot_widget.plot(self.time_history, self.flow_data, pen='b')

        gearpump_control_panel.addWidget(self.pump_flow_plot_widget)

        # Add gear pump control panel to the main layout
        gearpump_layout.addLayout(gearpump_control_panel)
        
        # Label to display the pressure value
        self.pressure_label = QLabel("Pressure: --- MPa", self)
        gearpump_layout.addWidget(self.pressure_label)

        # Pressure plot setup
        self.pressure_plot_widget = pg.PlotWidget(title="Inlet Pressure Over Time")
        self.pressure_plot_widget.setLabel('left', 'Pressure (MPa)')
        self.pressure_plot_widget.setLabel('bottom', 'Time (s)')
        self.pressure_plot_widget.setYRange(0, 1)  # Set y-axis from 0 to 1 MPa
        self.pressure_curve = self.pressure_plot_widget.plot(self.time_history, self.pressure_history, pen='y')

        gearpump_layout.addWidget(self.pressure_plot_widget)
        main_layout.addLayout(gearpump_layout)

        # Left side layout for voltage display (both label and plot)
        display_layout = QVBoxLayout()

        # Power supply state and measured power display in the same line
        power_info_layout = QHBoxLayout()
        
        self.power_state_label = QLabel("Power Supply State: ---", self)
        power_info_layout.addWidget(self.power_state_label)
        
        self.measured_power_label = QLabel("Measured Power: --- W", self)
        power_info_layout.addWidget(self.measured_power_label)
        
        display_layout.addLayout(power_info_layout)

        # Set current control
        set_current_layout = QHBoxLayout()
        self.set_current_spinbox = QDoubleSpinBox(self)
        self.set_current_spinbox.setRange(0, 20)  # Adjust the range as needed
        self.set_current_spinbox.setValue(0)
        set_current_layout.addWidget(QLabel("Set Current (A):", self))
        set_current_layout.addWidget(self.set_current_spinbox)

        self.set_current_button = QPushButton("Set Current", self)
        self.set_current_button.clicked.connect(self.set_power_supply_current)
        set_current_layout.addWidget(self.set_current_button)

        display_layout.addLayout(set_current_layout)

        # Set voltage control
        set_voltage_layout = QHBoxLayout()
        self.set_voltage_spinbox = QDoubleSpinBox(self)
        self.set_voltage_spinbox.setRange(0, 200)  # Adjust the range as needed
        self.set_voltage_spinbox.setValue(0)
        set_voltage_layout.addWidget(QLabel("Set Voltage (V):", self))
        set_voltage_layout.addWidget(self.set_voltage_spinbox)

        self.set_voltage_button = QPushButton("Set Voltage", self)
        self.set_voltage_button.clicked.connect(self.set_power_supply_voltage)
        set_voltage_layout.addWidget(self.set_voltage_button)

        display_layout.addLayout(set_voltage_layout)

        # Turn on/off power supply buttons
        self.turn_on_button = QPushButton("Turn On Power Supply", self)
        self.turn_on_button.clicked.connect(self.power_supply_worker.turn_on)
        display_layout.addWidget(self.turn_on_button)

        self.turn_off_button = QPushButton("Turn Off Power Supply", self)
        self.turn_off_button.clicked.connect(self.power_supply_worker.turn_off)
        display_layout.addWidget(self.turn_off_button)

        # Measured current and voltage display in the same line
        measured_info_layout = QHBoxLayout()
        
        self.measured_current_label = QLabel("Measured Current: --- A", self)
        measured_info_layout.addWidget(self.measured_current_label)
        
        self.measured_voltage_label = QLabel("Measured Voltage: --- V", self)
        measured_info_layout.addWidget(self.measured_voltage_label)
        
        display_layout.addLayout(measured_info_layout)

        # Power supply voltage and current real-time plot setup
        self.ps_plot_widget = pg.PlotWidget(title="Power Supply Voltage and Current Over Time")
        self.ps_plot_widget.setLabel('left', 'Voltage (V)')
        self.ps_plot_widget.setLabel('bottom', 'Time (s)')
        self.ps_plot_widget.setYRange(0, 50)  # Adjust the y-axis range for voltage as needed

        # Set the left axis color to match the voltage curve (blue)
        self.ps_plot_widget.getAxis('left').setPen(pg.mkPen(color='b'))  # 'b' represents blue

        # Create a second y-axis for current
        self.ps_plot_widget.showAxis('right')
        self.ps_plot_widget.setLabel('right', 'Current (A)')
        self.ps_plot_widget.getAxis('right').setPen(pg.mkPen(color='r'))

        # Create a new ViewBox for the second y-axis (current)
        self.current_viewbox = pg.ViewBox()
        self.ps_plot_widget.scene().addItem(self.current_viewbox)
        self.ps_plot_widget.getAxis('right').linkToView(self.current_viewbox)

        # Set the range for the second y-axis (current)
        self.current_viewbox.setYRange(0, 10)  # Set range for current from 0 to 0.5 A

        # Create curves for voltage and current
        self.ps_voltage_curve = self.ps_plot_widget.plot(self.time_history, self.ps_voltage, pen='b', name='Voltage')

        # Create the current curve in the second ViewBox
        self.ps_current_curve = pg.PlotCurveItem(self.time_history, self.ps_current, pen=pg.mkPen(color='r'), name='Current')
        self.current_viewbox.addItem(self.ps_current_curve)  # Add current curve to the ViewBox
        self.ps_current_curve.setZValue(1)  # Ensure current curve is on top

        # Sync the x-axis of the voltage and current plots
        self.ps_plot_widget.getViewBox().sigResized.connect(self.update_views)

        # Add legend to the plot
        self.ps_plot_widget.addLegend()

        # Add plot widget to the layout
        display_layout.addWidget(self.ps_plot_widget)

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

        # Add the pressure display (label + plot) to the center left of the main layout
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
        leak_layout = QHBoxLayout()
        self.leak_label = QLabel("Leak Status: ---", self)
        self.leak_indicator = QFrame(self)
        self.leak_indicator.setFixedSize(20, 20)
        self.leak_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
        leak_layout.addWidget(self.leak_label)
        leak_layout.addWidget(self.leak_indicator)
        control_layout.addLayout(leak_layout)

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

        # Test layout
        test_layout = QHBoxLayout()

        # Button to start data saving
        self.start_saving_button = QPushButton("Open data saving", self)
        self.start_saving_button.clicked.connect(self.start_saving)
        test_layout.addWidget(self.start_saving_button)

        # Button to close data saving
        self.close_button = QPushButton("Close data saving", self)
        self.close_button.clicked.connect(self.close_saving)
        test_layout.addWidget(self.close_button)

        # Horizontal layout for intermittent operation
        intermittent_operation_layout = QHBoxLayout()
        intermittent_operation_label = QLabel("Intermittent Operation: ", self)
        intermittent_operation_layout.addWidget(intermittent_operation_label)

        self.io_start_button = QPushButton("Start", self)
        self.io_start_button.clicked.connect(self.io_worker_start)
        intermittent_operation_layout.addWidget(self.io_start_button)

        self.io_stop_button = QPushButton("Stop", self)
        self.io_stop_button.clicked.connect(self.io_worker_stop)
        intermittent_operation_layout.addWidget(self.io_stop_button)

        self.io_reset_button = QPushButton("Reset", self)
        self.io_reset_button.clicked.connect(self.io_worker_reset)
        intermittent_operation_layout.addWidget(self.io_reset_button)

        self.io_show_button = QPushButton("Show", self)
        self.io_show_button.clicked.connect(self.show_intermit_dialog)
        intermittent_operation_layout.addWidget(self.io_show_button)

        # self.test1_button = QPushButton("Test 1", self)
        # self.test1_button.clicked.connect(self.update_intermittent_message)
        # intermittent_operation_layout.addWidget(self.test1_button)

        test_layout.addLayout(intermittent_operation_layout)

        control_layout.addLayout(test_layout)

        # Button to stop info display
        self.stop_display_button = QPushButton("Stop Info Display", self)
        self.stop_display_button.clicked.connect(self.stop_display)
        control_layout.addWidget(self.stop_display_button)

        # Add the control layout to the main layout (right side)
        main_layout.addLayout(control_layout)

        # Set the main layout for the window
        self.setLayout(main_layout)

        # Create the dialog instance
        self.inter_op_dialog = IntermittentOperationDialog(self.io_interval)

    def show_intermit_dialog(self):
        """Show the intermittent operation dialog."""
        self.inter_op_dialog.show()
    
    def update_dialog_plots(self, available_power, reactor_states):
        """Receive real-time updates from InterOpWorker and pass them to the dialog for plotting."""
        running_reactors = len(reactor_states)  # Count reactors currently running (assuming True indicates active)
        time_step = len(self.inter_op_dialog.time_data)  # Use length of time data for time axis
        self.inter_op_dialog.update_plots(time_step, available_power, running_reactors)

    def update_views(self):
        """Sync the second y-axis with the main plot when resizing occurs."""
        self.current_viewbox.setGeometry(self.ps_plot_widget.getViewBox().sceneBoundingRect())
        self.current_viewbox.linkedViewChanged(self.ps_plot_widget.getViewBox(), self.current_viewbox.XAxis)

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

        self.relay_control_worker.button_clicked.emit(channels, states)

    def update_leak_status(self, leak_detected):
        if leak_detected:
            self.leak_label.setText("Leak Status: Leak Detected")
            self.leak_indicator.setStyleSheet("background-color: red; border-radius: 10px;")
        else:
            self.leak_label.setText("Leak Status: No Leak Detected")
            self.leak_indicator.setStyleSheet("background-color: green; border-radius: 10px;")

    def update_pressure(self, pressure, cur_time):
        self.pressure_label.setText(f"Inlet pressure of reactor: {pressure:.3f} MPa")

    def update_plots(self, data):
        """Update both the pressure and voltage plots."""
        pressure_history = data['pressure']
        voltage_data = data['voltages']
        flow_history = data['flow_rate']
        ps_current = data['ps_current']
        ps_voltage = data['ps_voltage']
        self.ps_current = ps_current
        self.ps_voltage = ps_voltage
        self.pressure_history = pressure_history
        self.voltage_data = voltage_data

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

        #update the power supply voltage and current plot
        self.ps_voltage_curve.setData(self.time_history, ps_voltage)
        self.ps_current_curve.setData(self.time_history, ps_current)

    def toggle_voltage_curve(self):
        """Update the voltage plot when channel selection changes."""
        self.update_plots({'pressure': self.pressure_history, 'voltages': self.voltage_data, 'ps_current': self.ps_current, 'ps_voltage': self.ps_voltage})

    def update_voltages(self, voltages, cur_time):
        for i, voltage in enumerate(voltages[:10]):
            self.voltage_labels[i].setText(f"Voltage {i+1}: {voltage:.2f} V")

    def toggle_servo_position(self, servo_id, checked):
        position = 3071 if checked else 2047
        self.servo_control_worker.write_position_signal.emit(servo_id, position)

    def slider_moved(self, servo_id, position):
        self.servo_control_worker.write_position_signal.emit(servo_id, position)

    def update_servo_info(self, servo_id, pos, speed, load, temp):
        # Update the specific servo's info label and slider
        info_label = self.findChild(QLabel, f"servo_info_{servo_id}")
        position_slider = self.findChild(QSlider, f"servo_slider_{servo_id}")
        switch_button = self.findChild(QPushButton, f"servo_button_{servo_id}")

        if info_label and position_slider and switch_button:
            info_label.setText(f"Servo {servo_id} - Position: {pos}, Speed: {speed}, Load: {load}, T: {temp} ℃")
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
        try:
            self.io_worker.receive_relay_state(states)
        except:
            pass

    def update_pump_pressure(self, pressure):
        self.gearpump_pressure_label.setText(f"P: {pressure:.2f} Bar")
    
    def update_pump_flow_rate(self, flow, cur_time):
        self.gearpump_flow_rate_label.setText(f"FR: {flow} mL/min")

    def update_pump_rotate_rate(self, rotate_rate):
        self.gearpump_rotate_rate_label.setText(f"RR: {rotate_rate} RPM")

    def update_pump_temperature(self, temperature):
        self.gearpump_temperature_label.setText(f"T: {temperature:.2f} °C")
    
    def update_pump_state(self, state):
        self.gearpump_state_label.setText(f"Pump State: {state}")
    
    def set_gearpump_flow_rate(self):
        flow_rate = self.flow_rate_spinbox.value()
        self.gearpump_worker.flow_rate_set.emit(flow_rate)

    def set_gearpump_rotate_rate(self):
        rotate_rate = self.rotate_rate_spinbox.value()
        self.gearpump_worker.rotate_rate_set.emit(rotate_rate)

    def start_gearpump(self):
        self.gearpump_worker.start_pump_set.emit(1)

    def stop_gearpump(self):
        self.gearpump_worker.stop_pump_set.emit(0)

    def update_ps_state(self, state):
        self.power_state_label.setText(f"Power Supply State: {state}")
    
    def update_ps_current(self, current, cur_time):   
        self.measured_current_label.setText(f"Measured Current: {current} A")

    def update_ps_voltage(self, voltage, cur_time):
        self.measured_voltage_label.setText(f"Measured Voltage: {voltage} V")

    def update_ps_power(self, power):
        self.measured_power_label.setText(f"Measured Power: {power} W")

    def set_power_supply_current(self):
        current = self.set_current_spinbox.value()
        self.power_supply_worker.set_current_signal.emit(current)

    def set_power_supply_voltage(self): 
        voltage = self.set_voltage_spinbox.value()
        self.power_supply_worker.set_voltage_signal.emit(voltage)
    
    def stop_display(self):
        self.relay_control_worker.stopped.emit()
        self.data_updater_worker.stopped.emit()
        self.gearpump_worker.pump_stopped.emit()
        self.servo_control_worker.servo_stopped.emit()
        self.power_supply_worker.ps_stopped.emit()
        self.voltage_collector_worker.stopped.emit()
        self.error_processing_worker.stopped.emit()
    
    def start_saving(self):
        self.data_updater_worker.start_storing_signal.emit()

    def close_saving(self):
        self.data_updater_worker.stop_storing_signal.emit()

    def io_worker_start(self):
        # Check if the thread already exists and is running
        self.io_worker = InterOpWorker(self.io_interval, 'onemin-Ground-2018-01-03.csv', self.relay_control_worker, self.servo_control_worker, self.gearpump_worker, self.power_supply_worker)

        # Create a new QThread instance
        self.io_worker_thread = QThread()

        # Move the worker to the new thread
        self.io_worker.moveToThread(self.io_worker_thread)

        # Connect signals and slots
        self.io_worker_thread.started.connect(self.io_worker.run)
        self.io_worker_thread.finished.connect(self.io_worker_thread.deleteLater)
        self.io_worker.solar_reactor_signal.connect(self.update_dialog_plots)
        self.io_worker.finished.connect(self.data_updater_worker.stop_storing_data)
        self.io_worker.finished.connect(self.io_worker.deleteLater)
        self.io_worker.first_run_signal.connect(self.data_updater_worker.collect_inital_voltage)
        self.data_updater_worker.initial_voltage_signal.connect(self.io_worker.process_voltage_variation)
        self.data_updater_worker.update_electrolysis_volt_var.connect(self.io_worker.process_voltage_variation)
        #self.io_worker.stopped_signal.connect(self.io_worker.stop)
        #self.relay_control_worker.relay_state_updated.connect(self.io_worker.receive_relay_state)

        # Start the thread
        self.data_updater_worker.start_storing_signal.emit()
        self.io_worker_thread.start()
    
    def io_worker_stop(self):
        # Check if the thread is running before attempting to stop it
        if self.io_worker_thread.isRunning():
            # Stop the worker
            self.io_worker.stopped_signal.emit()
            time.sleep(2)
            # Quit and wait for the thread to finish
            self.io_worker_thread.quit()
            self.io_worker_thread.wait()
    
    def io_worker_reset(self):
        # Check if the thread is running before attempting to stop it
        try:
            if self.io_worker_thread.isRunning():
                # Stop the worker
                self.io_worker.stopped_signal.emit()
                time.sleep(2)
                # Quit and wait for the thread to finish
                self.io_worker_thread.quit()
                self.io_worker_thread.wait()
        except:
            pass
        self.inter_op_dialog.time_data = []
        self.inter_op_dialog.dc_power_data = []
        self.inter_op_dialog.reactor_data = []    

    def closeEvent(self, event):
        self.error_processing_thread.quit()
        self.error_processing_thread.wait()
        self.power_supply_thread.quit()
        self.power_supply_thread.wait()
        self.servo_thread.quit()
        self.servo_thread.wait()
        self.voltage_thread.quit()
        self.voltage_thread.wait()
        self.leakage_sensor_thread.stop()
        self.pressure_sensor_thread.stop()
        self.relay_control_thread.quit()
        self.relay_control_thread.wait()
        self.gearpump_thread.quit()
        self.gearpump_thread.wait()
        self.data_updater_thread.quit()
        self.data_updater_thread.wait()
        self.portHandler.closePort()
        self.gearpump_control.close_serial()
        self.voltage_collector.close_connection()
        self.leakage_sensor.close_connection()
        self.pressure_sensor.close_connection()
        self.relay_control.close_connection()
        self.power_supply.close_connection()
        event.accept()

# Main program
if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = MainGUI()
    gui.show()
    sys.exit(app.exec())
