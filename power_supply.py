from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
import serial
import time

class PowerSupplyControl:
    def __init__(self, port='COM17', baudrate=19200, address=1):
        self.port = port
        self.baudrate = baudrate
        self.address = address  # Power supply device address
        self.ser = None

    def open_connection(self):
        """Open the serial connection to the power supply."""
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=2  # Timeout in seconds
        )

    def close_connection(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send_command(self, command):
        """Send a command to the power supply."""
        if self.ser and self.ser.is_open:
            full_command = f"ADDR {self.address}:{command}\n"
            self.ser.write(full_command.encode('utf-8'))

    def read_response(self):
        """Read the response from the power supply."""
        if self.ser and self.ser.is_open:
            response = self.ser.readline().decode('utf-8').strip()
            if f"ADDR 001:" in response:
                return response.replace(f"ADDR 001:", "").strip()
            return response

    # Power supply ON/OFF control
    def turn_on(self):
        """Turn the power supply ON."""
        self.send_command("OUTP ON")

    def turn_off(self):
        """Turn the power supply OFF."""
        self.send_command("OUTP OFF")

    def read_state(self):
        """Read whether the power supply output is ON or OFF."""
        self.send_command("OUTP?")
        return self.read_response()

    # Read measured values
    def read_current(self):
        """Read the measured current from the power supply."""
        self.send_command("MEAS:CURR?")
        return self.read_response()

    def read_voltage(self):
        """Read the measured voltage from the power supply."""
        self.send_command("MEAS:VOLT?")
        return self.read_response()

    def read_power(self):
        """Read the measured power from the power supply."""
        self.send_command("MEAS:POW?")
        return self.read_response()

    # Read set values
    def read_set_current(self):
        """Read the set value of current from the power supply."""
        self.send_command("CURR?")
        return self.read_response()

    def read_set_voltage(self):
        """Read the set value of voltage from the power supply."""
        self.send_command("VOLT?")
        return self.read_response()

    # Set current and voltage
    def set_current(self, value):
        """Set the current to a specific value."""
        self.send_command(f"CURR {value}")

    def set_voltage(self, value):
        """Set the voltage to a specific value."""
        self.send_command(f"VOLT {value}")


class PowerSupplyControlThread(QThread):
    power_state_updated = Signal(str)  # Signal to update power supply state in the GUI
    current_measured = Signal(str)     # Signal to send current measurements
    voltage_measured = Signal(str)     # Signal to send voltage measurements
    power_measured = Signal(str)       # Signal to send power measurements
    current_set = Signal(str)          # Signal to indicate the current has been set
    voltage_set = Signal(str)          # Signal to indicate the voltage has been set

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
                    self.power_state_updated.emit(state)

                    # Read measured current
                    current = self.power_control.read_current()
                    self.current_measured.emit(current)

                    # Read measured voltage
                    voltage = self.power_control.read_voltage()
                    self.voltage_measured.emit(voltage)

                    # Read measured power
                    power = self.power_control.read_power()
                    self.power_measured.emit(power)
                except Exception as e:
                    print(f"Error reading power supply measurements: {e}")
                self.msleep(1000)  # Poll every second

    def turn_on(self):
        """Send the command to turn ON the power supply."""
        with QMutexLocker(self.mutex):
            try:
                self.power_control.turn_on()
                self.power_state_updated.emit("ON")
            except Exception as e:
                print(f"Error turning on the power supply: {e}")

    def turn_off(self):
        """Send the command to turn OFF the power supply."""
        with QMutexLocker(self.mutex):
            try:
                self.power_control.turn_off()
                self.power_state_updated.emit("OFF")
            except Exception as e:
                print(f"Error turning off the power supply: {e}")

    def set_current(self, value):
        """Set the current of the power supply."""
        with QMutexLocker(self.mutex):
            try:
                self.power_control.set_current(value)
                self.current_set.emit(f"Current set to {value} A")
            except Exception as e:
                print(f"Error setting current: {e}")

    def set_voltage(self, value):
        """Set the voltage of the power supply."""
        with QMutexLocker(self.mutex):
            try:
                self.power_control.set_voltage(value)
                self.voltage_set.emit(f"Voltage set to {value} V")
            except Exception as e:
                print(f"Error setting voltage: {e}")

    def stop(self):
        """Stop the thread."""
        self.running = False
        self.wait()


