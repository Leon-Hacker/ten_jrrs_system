from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
import serial
import time
import logging

# Configure a logger for the power supply
power_logger = logging.getLogger('PowerSupplyControl')
power_handler = logging.FileHandler('power_supply.log')
power_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
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

class PowerSupplyControlThread(QThread):
    power_state_updated = Signal(str)  # Signal to update power supply state in the GUI
    current_measured = Signal(str, float)     # Signal to send current measurements
    voltage_measured = Signal(str, float)     # Signal to send voltage measurements
    power_measured = Signal(str)       # Signal to send power measurements
    current_set_response = Signal()    # Signal to reaturn current set response
    voltage_set_response = Signal()    # Signal to return voltage set response
    turn_on_response = Signal()        # Signal to return power supply ON response
    turn_off_response = Signal()       # Signal to return power supply OFF response

    def __init__(self, power_control, parent=None):
        super().__init__(parent)
        self.power_control = power_control
        self.running = True
        self.mutex = QMutex()  # QMutex to ensure thread safety

    def run(self):
        """Continuously monitor the power supply's current, voltage, and power."""
        while self.running:
            with QMutexLocker(self.mutex):  # Ensure safe access to the critical section
                try:
                    # Read the power state
                    state = self.power_control.read_state()
                    if state == "1":
                        state = "ON"
                    else:
                        state = "OFF"
                    self.power_state_updated.emit(state)
                    self.msleep(50)

                    # Read measured current
                    current = self.power_control.read_current()
                    cur_time = time.time()
                    self.current_measured.emit(current, cur_time)
                    self.msleep(50)

                    # Read measured voltage
                    voltage = self.power_control.read_voltage()
                    cur_time = time.time()
                    self.voltage_measured.emit(voltage, cur_time)
                    self.msleep(50)

                    # Read measured power
                    power = self.power_control.read_power()
                    self.power_measured.emit(power)
                    self.msleep(50)
                except Exception as e:
                    print(f"Error reading power supply measurements: {e}")
                self.msleep(800)  

    def turn_on(self):
        """Send the command to turn ON the power supply."""
        with QMutexLocker(self.mutex):
            try:
                self.power_control.turn_on()
            except Exception as e:
                print(f"Error turning on the power supply: {e}")

    def turn_off(self):
        """Send the command to turn OFF the power supply."""
        with QMutexLocker(self.mutex):
            try:
                self.power_control.turn_off()
            except Exception as e:
                print(f"Error turning off the power supply: {e}")

    def set_current(self, value):
        """Set the current of the power supply."""
        with QMutexLocker(self.mutex):
            try:
                self.power_control.set_current(value)
            except Exception as e:
                print(f"Error setting current: {e}")

    def set_voltage(self, value):
        """Set the voltage of the power supply."""
        with QMutexLocker(self.mutex):
            try:
                self.power_control.set_voltage(value)
            except Exception as e:
                print(f"Error setting voltage: {e}")

    def stop(self):
        """Stop the thread."""
        self.running = False
        self.wait()


