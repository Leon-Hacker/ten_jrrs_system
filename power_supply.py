from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker, QTimer, QObject, QThread
import serial
import time
import logging
from logging.handlers import RotatingFileHandler

# Configure a logger for the power supply with size-based rotation
power_logger = logging.getLogger('PowerSupplyControl')
power_handler = RotatingFileHandler(
    'logs/power_supply.log',
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=5,         # Keep up to 5 backup files
    encoding='utf-8'
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
power_handler.setFormatter(formatter)
power_logger.addHandler(power_handler)
power_logger.setLevel(logging.INFO)

class PowerSupplyControl:
    def __init__(self, port='COM17', baudrate=19200, address=1):
        self.port = port
        self.baudrate = baudrate
        self.address = address  # Power supply device address
        self.ser = None
        power_logger.info("PowerSupplyControl initialized with port %s, baudrate %d, address %d", port, baudrate, address)

    def open_connection(self):
        """Open the serial connection to the power supply."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=2  # Timeout in seconds
            )
            power_logger.info("Opened connection on port %s", self.port)
        except serial.SerialException as e:
            power_logger.error("Failed to open connection on port %s: %s", self.port, str(e))

    def close_connection(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            power_logger.info("Closed connection on port %s", self.port)

    def send_command(self, command):
        """Send a command to the power supply."""
        if self.ser and self.ser.is_open:
            full_command = f"ADDR {self.address}:{command}\n"
            self.ser.write(full_command.encode('utf-8'))
            power_logger.info("Sent command to power supply: %s", command)

    def read_response(self):
        """Read the response from the power supply."""
        if self.ser and self.ser.is_open:
            response = self.ser.readline().decode('utf-8').strip()
            power_logger.info("Received response from power supply: %s", response)
            if f"ADDR 001:" in response:
                return response.replace(f"ADDR 001:", "").strip()
            return response

    # Power supply ON/OFF control
    def turn_on(self):
        """Turn the power supply ON."""
        self.send_command("OUTP ON")
        power_logger.info("Turned power supply ON")

    def turn_off(self):
        """Turn the power supply OFF."""
        self.send_command("OUTP OFF")
        power_logger.info("Turned power supply OFF")

    def read_state(self):
        """Read whether the power supply output is ON or OFF."""
        self.ser.reset_input_buffer()
        self.send_command("OUTP?")
        state = self.read_response()
        power_logger.info("Power supply state read as: %s", state)
        return state

    # Read measured values
    def read_current(self):
        """Read the measured current from the power supply."""
        self.ser.reset_input_buffer()
        self.send_command("MEAS:CURR?")
        current = self.read_response()
        power_logger.info("Measured current: %s", current)
        return current

    def read_voltage(self):
        """Read the measured voltage from the power supply."""
        self.ser.reset_input_buffer()
        self.send_command("MEAS:VOLT?")
        voltage = self.read_response()
        power_logger.info("Measured voltage: %s", voltage)
        return voltage

    def read_power(self):
        """Read the measured power from the power supply."""
        self.ser.reset_input_buffer()
        self.send_command("MEAS:POW?")
        power = self.read_response()
        power_logger.info("Measured power: %s", power)
        return power

    # Read set values
    def read_set_current(self):
        """Read the set value of current from the power supply."""
        self.ser.reset_input_buffer()
        self.send_command("CURR?")
        set_current = self.read_response()
        power_logger.info("Set current value: %s", set_current)
        return set_current

    def read_set_voltage(self):
        """Read the set value of voltage from the power supply."""
        self.ser.reset_input_buffer()
        self.send_command("VOLT?")
        set_voltage = self.read_response()
        power_logger.info("Set voltage value: %s", set_voltage)
        return set_voltage

    # Set current and voltage
    def set_current(self, value):
        """Set the current to a specific value."""
        self.send_command(f"CURR {value}")
        power_logger.info("Set current to %s", value)

    def set_voltage(self, value):
        """Set the voltage to a specific value."""
        self.send_command(f"VOLT {value}")
        power_logger.info("Set voltage to %s", value)

class PowerSupplyWorker(QObject):
    # ----------------------
    #       SIGNALS
    # ----------------------
    power_state_updated = Signal(str)      # Signal to update power supply state in the GUI
    current_measured = Signal(str, float)  # Signal to send current measurements (value, timestamp)
    voltage_measured = Signal(str, float)  # Signal to send voltage measurements (value, timestamp)
    power_measured = Signal(str)           # Signal to send power measurements

    ps_stopped = Signal()                  # Signal to notify that the power supply worker has stopped
    button_checked = Signal(float)
    current_set_response = Signal()        # Signal to return current set response
    voltage_set_response = Signal()        # Signal to return voltage set response
    turn_on_response = Signal()            # Signal to return power supply ON response
    turn_off_response = Signal()           # Signal to return power supply OFF response

    set_voltage_signal = Signal(float)
    set_current_signal = Signal(float)

    def __init__(self, power_control, parent=None):
        super().__init__(parent)
        self.power_control = power_control
        self.running = True
        self.mutex = QMutex()  # QMutex to ensure thread safety
        # self.current_set = 0
        self.voltage_set = 0
        self.cur_state = None

        # Timer for periodic polling of power supply state
        self.poll_timer = None

    # ----------------------
    #   START MONITORING
    # ----------------------
    def start_monitoring(self):
        """
        Set up a QTimer to periodically poll the power supply's current, voltage, and power.
        This method should be called (or connected to the thread's started signal)
        after moving this worker to a QThread.
        """
        self.running = True
        if not self.poll_timer:
            self.poll_timer = QTimer()
            # e.g., poll every 700 ms, similar to the original loop's timing
            self.poll_timer.setInterval(700)
            self.poll_timer.timeout.connect(self.poll_power_supply)
        
        self.poll_timer.start()

    # ----------------------
    #   STOP MONITORING
    # ----------------------
    def stop(self):
        """
        Stop the monitoring process.
        """
        self.running = False
        # if self.poll_timer and self.poll_timer.isActive():
        #     self.poll_timer.stop()

    # ----------------------
    #   POLL POWER SUPPLY
    # ----------------------
    def poll_power_supply(self):
        """
        Periodically called by QTimer to read the power supply state, current, voltage, and power,
        then emit the appropriate signals to the GUI.
        """
        if not self.running:
            # If the worker is asked to stop, stop the timer
            if self.poll_timer:
                self.poll_timer.stop()
            return
        
        QThread.msleep(50)  

        with QMutexLocker(self.mutex):
            try:
                # 1. Read the power state
                state = self.power_control.read_state()
                if state == "1":
                    state = "ON"
                else:
                    state = "OFF"
                self.power_state_updated.emit(state)
                self.cur_state = state
                QThread.msleep(50)

                # 2. Read measured current
                current_value = self.power_control.read_current()
                cur_time = time.time()
                self.current_measured.emit(current_value, cur_time)
                QThread.msleep(50)

                # 3. Read measured voltage
                voltage_value = self.power_control.read_voltage()
                cur_time = time.time()
                self.voltage_measured.emit(voltage_value, cur_time)
                QThread.msleep(50)

                # 4. Read measured power
                power_value = self.power_control.read_power()
                self.power_measured.emit(power_value)
                QThread.msleep(50)

                # 5. Read set voltage
                self.voltage_set = float(self.power_control.read_set_voltage())
                print(f"Set voltage: {self.voltage_set}")

            except Exception as e:
                print(f"Error reading power supply measurements: {e}")
        
        QThread.msleep(50)

    # ----------------------
    #   CONTROL COMMANDS
    # ----------------------
    def turn_on(self):
        """
        Send the command to turn ON the power supply.
        """
        with QMutexLocker(self.mutex):
            try:
                self.power_control.turn_on()
                # Optionally emit a response signal for the GUI
                self.turn_on_response.emit()
            except Exception as e:
                print(f"Error turning on the power supply: {e}")

    def turn_off(self):
        """
        Send the command to turn OFF the power supply.
        """
        with QMutexLocker(self.mutex):
            try:
                self.power_control.turn_off()
                # Optionally emit a response signal for the GUI
                self.turn_off_response.emit()
            except Exception as e:
                print(f"Error turning off the power supply: {e}")

    def turn_off_checked(self):
        with QMutexLocker(self.mutex):
            try:
                self.power_control.turn_off()
            except Exception as e:
                print(f"Error turning off the power supply: {e}")
        QTimer.singleShot(1000, lambda: self.check_turn_off())

    def check_turn_off(self):
        with QMutexLocker(self.mutex):
            if self.cur_state == "OFF":
                return
            else:
                print("Power supply state is not OFF. Resending command.")
                try:
                    self.power_control.turn_off()
                except Exception as e:
                    print(f"Error turning off the power supply: {e}")
                QTimer.singleShot(1000, lambda: self.check_turn_off())

    def set_current(self, value):
        """
        Set the current of the power supply.
        """
        with QMutexLocker(self.mutex):
            try:
                self.power_control.set_current(value)
                # Optionally emit a response signal for the GUI
                self.current_set_response.emit()
            except Exception as e:
                print(f"Error setting current: {e}")

    def set_voltage(self, value):
        """
        Set the voltage of the power supply.
        """
        with QMutexLocker(self.mutex):
            try:
                self.power_control.set_voltage(value)
                # Optionally emit a response signal for the GUI
                self.voltage_set_response.emit()
            except Exception as e:
                print(f"Error setting voltage: {e}")

    def set_voltage_checked(self, value):
        with QMutexLocker(self.mutex):
            try:
                self.power_control.set_voltage(value)
            except Exception as e:
                print(f"Error setting voltage: {e}")
        QTimer.singleShot(1000, lambda: self.check_set_voltage(value))
    
    def check_set_voltage(self, value):
        with QMutexLocker(self.mutex):
            if self.voltage_set == value:
                return
            else:
                print("Voltage set value does not match the desired value. Resending command.")
                try:
                    self.power_control.set_voltage(value)
                except Exception as e:
                    print(f"Error setting voltage: {e}")
                QTimer.singleShot(1000, lambda: self.check_set_voltage(value))


