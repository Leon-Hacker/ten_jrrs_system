from scservo_sdk import *  # Import SCServo SDK library

class ServoControl:
    def __init__(self, scs_id, port_handler, packet_handler,
                 min_pos=0, max_pos=4095, moving_speed=2400, moving_acc=50):
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
