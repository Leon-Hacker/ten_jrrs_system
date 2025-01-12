import logging
from logging.handlers import RotatingFileHandler
from scservo_sdk import *  # Import SCServo SDK library
from PySide6.QtCore import QObject, Signal, QMutex, QMutexLocker, QTimer, QThread
import os
import gzip
import shutil

# Configure a logger for the servo controller with size-based rotation
servo_logger = logging.getLogger('ServoControl')
servo_handler = RotatingFileHandler(
    'logs/servo.log',
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=5,         # Keep up to 5 backup files
    encoding='utf-8'
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
servo_handler.setFormatter(formatter)
servo_logger.addHandler(servo_handler)
servo_logger.setLevel(logging.INFO)

class ModbusError(Exception):
    """Base class for Modbus exceptions."""
    pass

class CRCMismatchError(ModbusError):
    """Raised when CRC does not match."""
    pass

class ModbusExceptionError(ModbusError):
    """Raised when Modbus device returns an exception code."""
    pass

class GearPumpController:
    # ... [Same as before with open_serial and close_serial methods]
    pass

class ServoWorker(QObject):
    # ----------------------
    #        SIGNALS
    # ----------------------
    position_updated = Signal(int, int, int, int, int)  # Signal to update the GUI (servo_id, pos, speed, temp)
    write_position_signal = Signal(int, int)        # Signal to request a position write (servo_id, position)
    disable_torque_signal = Signal(int)            # Signal to request torque disable (servo_id)
    inter_open = Signal(int)
    inter_close = Signal(int)
    tor_close = Signal(int)
    tor_open = Signal(int)

    servo_stopped = Signal()  # Signal to notify that the servo worker has stopped
    button_checked_close = Signal(int)
    button_checked_open = Signal(int)
    button_checked_distorque = Signal(int)
    button_checked_distorque_close = Signal(int)
    button_checked_distorque_open = Signal(int)

    # ----------------------
    #        INIT
    # ----------------------
    def __init__(self, servos):
        """
        Worker class to handle servo operations in a separate thread.
        
        :param servos: Dictionary of ServoControl instances keyed by servo_id
        """
        super().__init__()
        self.servos = servos  # Dictionary of ServoControl instances
        self.mutex = QMutex()  # QMutex to ensure thread-safe operations
        self.running = True
        self.servos_pos = {scs_id: 0 for scs_id in servos.keys()}
        self.servos_load = {scs_id: 0 for scs_id in servos.keys()}

        # Connect signals to their respective slots
        self.write_position_signal.connect(self.write_position)
        self.disable_torque_signal.connect(self.disable_torque)

        servo_logger.info("ServoWorker initialized with servos: %s", list(servos.keys()))

    # ----------------------
    #        START
    # ----------------------
    def start(self):
        """
        Start the main loop for servo control. Should be called after moving to a thread.
        """
        servo_logger.info("ServoWorker started monitoring.")
        self.main_loop()

    # ----------------------
    #      MAIN LOOP
    # ----------------------
    def main_loop(self):
        """
        Main loop for servo control, periodically reading servo states.
        """
        self.poll_timer = QTimer()
        self.poll_timer.setInterval(200)  # Poll every 200 ms
        self.poll_timer.timeout.connect(self.poll_servos)
        self.poll_timer.start()

        # No need for an additional loop; QTimer handles periodic calls

    def poll_servos(self):
        """
        Poll each servo for its current state and emit signals to update the GUI.
        """
        # print(self.servos_pos)
        if not self.running:
            # If someone requested us to stop, then stop the timer
            self.poll_timer.stop()
            servo_logger.info("ServoWorker is stopping.")
            return
        
        QThread.msleep(50)

        with QMutexLocker(self.mutex):
            for scs_id, servo in self.servos.items():
                try:
                    pos, speed, load, volt, temp = servo.read_all()
                    self.servos_pos[scs_id] = pos
                    self.servos_load[scs_id] = load
                    self.position_updated.emit(scs_id, pos, speed, load, temp)
                    # if pos > 3000 and load != 0:
                    #     self.inter_close.emit(scs_id, pos)
                    # elif pos < 2200 and load != 0:
                    #     self.inter_open.emit(scs_id, pos)
                    servo_logger.info("Polled Servo %d: Position=%d, Speed=%d, Load=%d, Temp=%d°C", scs_id, pos, speed, load, temp)
                except Exception as e:
                    servo_logger.error("Error reading data from servo %d: %s", scs_id, str(e))
        
        QThread.msleep(50)

    # ----------------------
    #        STOP
    # ----------------------
    def stop(self):
        """
        Stop the worker from running.
        """
        servo_logger.info("ServoWorker received stop signal.")
        self.running = False
        # if hasattr(self, 'poll_timer') and self.poll_timer.isActive():
        #     self.poll_timer.stop()

    # ----------------------
    #    CONTROL COMMANDS
    # ----------------------
    def write_position(self, servo_id, position):
        """
        Slot to handle writing servo position.
        
        :param servo_id: ID of the servo to control
        :param position: Desired position to write
        """
        # print(servo_id, position)
        with QMutexLocker(self.mutex):
            try:
                self.servos[servo_id].write_position(position)
                servo_logger.info("Sent write_position to Servo %d: Position=%d", servo_id, position)
                
                # Schedule torque disable 12 seconds later (12000 ms)
                QTimer.singleShot(12000, lambda: self.disable_torque_signal.emit(servo_id))
            except Exception as e:
                servo_logger.error("Error writing position to servo %d: %s", servo_id, str(e))

    def disable_torque(self, servo_id):
        """
        Slot to handle disabling torque on a servo.
        
        :param servo_id: ID of the servo to control
        """
        with QMutexLocker(self.mutex):
            try:
                self.servos[servo_id].write_torque_disable()
                servo_logger.info("Disabled torque on Servo %d", servo_id)
            except Exception as e:
                servo_logger.error("Error disabling torque on servo %d: %s", servo_id, str(e))
    
    def write_position_checked_close(self, servo_id):
        with QMutexLocker(self.mutex):
            try:
                self.servos[servo_id].write_position(3100)
                servo_logger.info("Sent write_position to Servo %d: Position=3100", servo_id)
            except Exception as e:
                servo_logger.error("Error writing position to servo %d: %s", servo_id, str(e))
        # Check the servo positin and resend command if necessary
        QTimer.singleShot(3500, lambda: self.check_position_close(servo_id))

    def check_position_close(self, servo_id):
        with QMutexLocker(self.mutex):
            if self.servos_pos[servo_id] >= 3000:
                self.inter_close.emit(servo_id)
                return
            else:
                print("Servo position does not match the desired position. Resending command.")
                try:
                    self.servos[servo_id].write_position(3100)
                except Exception as e:
                    print(f"Error writing position to servo {servo_id}: {e}")
                
                QTimer.singleShot(1000, lambda: self.check_position_close(servo_id))
    
    def write_position_checked_open(self, servo_id):
        with QMutexLocker(self.mutex):
            try:
                self.servos[servo_id].write_position(2030)
                servo_logger.info("Sent write_position to Servo %d: Position=2030", servo_id)
            except Exception as e:
                servo_logger.error("Error writing position to servo %d: %s", servo_id, str(e))
        # Check the servo positin and resend command if necessary
        QTimer.singleShot(3500, lambda: self.check_position_open(servo_id))

    def check_position_open(self, servo_id):
        with QMutexLocker(self.mutex):
            if self.servos_pos[servo_id] <= 2200:
                self.inter_open.emit(servo_id)
                return
            else:
                print("Servo position does not match the desired position. Resending command.")
                try:
                    self.servos[servo_id].write_position(2030)
                except Exception as e:
                    print(f"Error writing position to servo {servo_id}: {e}")
                
                QTimer.singleShot(1000, lambda: self.check_position_open(servo_id))

    def disable_torque_checked_close(self, servo_id):
        with QMutexLocker(self.mutex):
            try:
                self.servos[servo_id].write_torque_disable()
                servo_logger.info("Disabled torque on Servo %d", servo_id)
            except Exception as e:
                servo_logger.error("Error disabling torque on servo %d: %s", servo_id, str(e))
        # Check the servo positin and resend command if necessary
        QTimer.singleShot(1000, lambda: self.check_torque_close(servo_id))
    
    def check_torque_close(self, servo_id):
        with QMutexLocker(self.mutex):
            if self.servos_load[servo_id] == 0:
                self.tor_close.emit(servo_id)
                return
            else:
                print("Servo torque is not disabled. Resending command.")
                try:
                    self.servos[servo_id].write_torque_disable()
                except Exception as e:
                    print(f"Error disabling torque on servo {servo_id}: {e}")
                
                QTimer.singleShot(1000, lambda: self.check_torque_close(servo_id))

    def disable_torque_checked_open(self, servo_id):
        with QMutexLocker(self.mutex):
            try:
                self.servos[servo_id].write_torque_disable()
                servo_logger.info("Disabled torque on Servo %d", servo_id)
            except Exception as e:
                servo_logger.error("Error disabling torque on servo %d: %s", servo_id, str(e))
        # Check the servo positin and resend command if necessary
        QTimer.singleShot(1000, lambda: self.check_torque_open(servo_id))
    
    def check_torque_open(self, servo_id):
        with QMutexLocker(self.mutex):
            if self.servos_load[servo_id] == 0:
                self.tor_open.emit(servo_id)
                return
            else:
                print("Servo torque is not disabled. Resending command.")
                try:
                    self.servos[servo_id].write_torque_disable()
                except Exception as e:
                    print(f"Error disabling torque on servo {servo_id}: {e}")
                
                QTimer.singleShot(1000, lambda: self.check_torque_open(servo_id))


class ServoControl:
    def __init__(self, scs_id, port_handler, packet_handler,
                 min_pos=2030, max_pos=3100, moving_speed=200, moving_acc=50):
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