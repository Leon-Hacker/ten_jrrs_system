import sys
import os

if os.name == 'nt':
    import msvcrt
    def getch():
        return msvcrt.getch().decode()
else:
    import sys, tty, termios
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    def getch():
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

sys.path.append("..")
from scservo_sdk import *                       # Uses SCServo SDK library
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

class ServoThread(QThread):
    position_updated = Signal(int, int, int)  # Signal to update the GUI (servo_id, pos, speed)
    write_position_signal = Signal(int, int)  # Signal to request a position write

    def __init__(self, port_handler, packet_handler, parent=None):
        super().__init__(parent)
        self.port_handler = port_handler
        self.packet_handler = packet_handler
        self.mutex = QMutex()  # QMutex to ensure reading and writing don't run concurrently
        self.running = True
        self.write_position_signal.connect(self.write_position)  # Connect signal to slot

    def run(self):
        """Main loop for servo control."""
        groupSyncRead = GroupSyncRead(self.packet_handler, SMS_STS_PRESENT_POSITION_L, 4)
        num_servos = 10  # Assuming 10 servos

        while self.running:
            # Use QMutexLocker to ensure safe access to the critical section
            with QMutexLocker(self.mutex):
                try:
                    # Add parameter storage for SCServo#1~10 present position value
                    for scs_id in range(1, num_servos + 1):
                        if not groupSyncRead.addParam(scs_id):
                            print(f"[ID:{scs_id:03d}] groupSyncRead addparam failed")

                    scs_comm_result = groupSyncRead.txRxPacket()
                    if scs_comm_result != COMM_SUCCESS:
                        print(f"{self.packet_handler.getTxRxResult(scs_comm_result)}")

                    for scs_id in range(1, num_servos + 1):
                        # Check if groupsyncread data of SCServo#1~10 is available
                        scs_data_result, scs_error = groupSyncRead.isAvailable(scs_id, SMS_STS_PRESENT_POSITION_L, 4)
                        if scs_data_result:
                            # Get SCServo#scs_id present position and speed values
                            scs_present_position = groupSyncRead.getData(scs_id, SMS_STS_PRESENT_POSITION_L, 2)
                            scs_present_speed = groupSyncRead.getData(scs_id, SMS_STS_PRESENT_SPEED_L, 2)
                            self.position_updated.emit(scs_id, scs_present_position, self.packet_handler.scs_tohost(scs_present_speed, 15))
                        else:
                            print(f"[ID:{scs_id:03d}] groupSyncRead getdata failed")
                            continue
                        if scs_error != 0:
                            print(f"{self.packet_handler.getRxPacketError(scs_error)}")

                    groupSyncRead.clearParam()
                except Exception as e:
                    print(f"Error reading data from servos: {e}")

            self.msleep(500)  # Wait 500 ms between each iteration

    def stop(self):
        """Stop the thread."""
        self.running = False
        self.wait()  # Wait for the thread to finish

    def write_position(self, servo_id, position):
        """Slot to handle writing servo position."""
        # Use QMutexLocker to ensure safe access to the critical section
        with QMutexLocker(self.mutex):
            try:
                scs_comm_result, scs_error = self.packet_handler.WritePosEx(servo_id, position, 100, 50)  # Example speed and acceleration
                if scs_comm_result != COMM_SUCCESS:
                    raise Exception(f"Communication Error: {self.packet_handler.getTxRxResult(scs_comm_result)}")
                elif scs_error != 0:
                    raise Exception(f"Servo Error: {self.packet_handler.getRxPacketError(scs_error)}")
            except Exception as e:
                print(f"Error writing position to servo {servo_id}: {e}")

if __name__ == "__main__":
    try:
        port_handler = PortHandler('COM12')
        packet_handler = sms_sts(port_handler)

        # Open port
        if not port_handler.openPort():
            raise Exception("Failed to open the port")

        # Set port baudrate
        if not port_handler.setBaudRate(115200):
            raise Exception("Failed to change the baudrate")

        servo_thread = ServoThread(port_handler, packet_handler)
        servo_thread.start()

        print("Press any key to continue! (or press ESC to quit!)")
        while True:
            if getch() == chr(0x1b):
                servo_thread.stop()
                break

    except Exception as e:
        print(e)
    finally:
        port_handler.closePort()