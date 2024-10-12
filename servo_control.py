from scservo_sdk import *  # Import SCServo SDK library
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker, QTimer

class ServoThread(QThread):
    position_updated = Signal(int, int, int, int)  # Signal to update the GUI (servo_id, pos, speed)
    write_position_signal = Signal(int, int)  # Signal to request a position write
    disable_torque_signal = Signal(int)  # Signal to request torque disable

    def __init__(self, servos, parent=None):
        super().__init__(parent)
        self.servos = servos  # Dictionary of ServoControl instances
        self.mutex = QMutex()  # QMutex to ensure reading and writing don't run concurrently
        self.running = True
        self.write_position_signal.connect(self.write_position)  # Connect signal to slot
        self.disable_torque_signal.connect(self.disable_torque)  # Connect signal to slot

    def run(self):
        """Main loop for servo control."""
        while self.running:
            for scs_id, servo in self.servos.items():
                self.msleep(200)  # Wait 50 ms between each servo read to give time to the device to process the command
                # Use QMutexLocker to ensure safe access to the critical section
                with QMutexLocker(self.mutex):  
                    try:
                        # Safely read the servo's position and speed
                        pos, speed, load, volt, temp = servo.read_all()
                        # Emit signal to update GUI
                        self.position_updated.emit(scs_id, pos, speed, temp)
                    except Exception as e:
                        print(f"Error reading data from servo {scs_id}: {e}")
            self.msleep(200)  # Wait 100 ms between each iteration

    def stop(self):
        """Stop the thread."""
        self.running = False
        self.wait()  # Wait for the thread to finish

    def write_position(self, servo_id, position):
        """Slot to handle writing servo position."""
        # Use QMutexLocker to ensure safe access to the critical section
        with QMutexLocker(self.mutex):
            try:
                self.servos[servo_id].write_position(position)
                # Schedule torque disable 5 seconds later
                QTimer.singleShot(12000, lambda: self.disable_torque_signal.emit(servo_id))
            except Exception as e:
                print(f"Error writing position to servo {servo_id}: {e}")

    def disable_torque(self, servo_id):
        """Slot to handle disabling torque."""
        # Use QMutexLocker to ensure safe access to the critical section
        with QMutexLocker(self.mutex):
            try:
                self.servos[servo_id].write_torque_disable()
            except Exception as e:
                print(f"Error disabling torque on servo {servo_id}: {e}")

class ServoControl:
    def __init__(self, scs_id, port_handler, packet_handler,
                 min_pos=2030, max_pos=3100, moving_speed=100, moving_acc=50):
        # Servo configuration
        self.SCS_ID = scs_id
        self.SCS_MINIMUM_POSITION_VALUE = min_pos
        self.SCS_MAXIMUM_POSITION_VALUE = max_pos
        self.SCS_MOVING_SPEED = moving_speed
        self.SCS_MOVING_ACC = moving_acc

        # Use the shared port and packet handlers
        self.portHandler = port_handler
        self.packetHandler = packet_handler

    def write_position(self, position):
        """Write the goal position to the servo."""
        scs_comm_result, scs_error = self.packetHandler.WritePosEx(self.SCS_ID, position, self.SCS_MOVING_SPEED, self.SCS_MOVING_ACC)
        if scs_comm_result != COMM_SUCCESS:
            raise Exception(f"Communication Error: {self.packetHandler.getTxRxResult(scs_comm_result)}")
        elif scs_error != 0:
            raise Exception(f"Servo Error: {self.packetHandler.getRxPacketError(scs_error)}")

    def read_position_and_speed(self):
        """Read the current position and speed of the servo."""
        scs_present_position, scs_present_speed, scs_comm_result, scs_error = self.packetHandler.ReadPosSpeed(self.SCS_ID)
        if scs_comm_result != COMM_SUCCESS:
            raise Exception(f"Communication Error: {self.packetHandler.getTxRxResult(scs_comm_result)}")
        elif scs_error != 0:
            raise Exception(f"Servo Error: {self.packetHandler.getRxPacketError(scs_error)}")

        return scs_present_position, scs_present_speed
    
    def write_torque_disable(self):
        """Disable torque on the servo."""
        scs_comm_result, scs_error = self.packetHandler.TorqueDisable(self.SCS_ID)
        if scs_comm_result != COMM_SUCCESS:
            raise Exception(f"Communication Error: {self.packetHandler.getTxRxResult(scs_comm_result)}")
        elif scs_error != 0:
            raise Exception(f"Servo Error: {self.packetHandler.getRxPacketError(scs_error)}")
    
    def read_all(self):
        """Read the temperature of the servo."""
        scs_present_position, scs_present_speed, scs_present_load, scs_present_volt, scs_present_temp, scs_comm_result, scs_error  = self.packetHandler.ReadPos_Spd_Load_Volt_Temp(self.SCS_ID)
        if scs_comm_result != COMM_SUCCESS:
            raise Exception(f"Communication Error: {self.packetHandler.getTxRxResult(scs_comm_result)}")
        elif scs_error != 0:
            raise Exception(f"Servo Error: {self.packetHandler.getRxPacketError(scs_error)}")
        
        return scs_present_position, scs_present_speed, scs_present_load, scs_present_volt, scs_present_temp