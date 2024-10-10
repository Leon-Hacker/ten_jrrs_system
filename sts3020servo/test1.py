# test1.py

import sys
from scservo_sdk import *  # Uses SCServo SDK library
import os

# Default settings (adjust as per your existing code)
SCS_ID = 1
BAUDRATE = 115200
DEVICENAME = 'COM12'  # Replace with your device's COM port

# Initialize PortHandler and PacketHandler
portHandler = PortHandler(DEVICENAME)
packetHandler = sms_sts(portHandler)

# Open port and set baudrate
if not portHandler.openPort():
    print("Failed to open the port")
    sys.exit()

if not portHandler.setBaudRate(BAUDRATE):
    print("Failed to set baudrate")
    sys.exit()

# Function to enable torque
def torque_enable(scs_id):
    scs_comm_result, scs_error = packetHandler.TorqueEnable(scs_id, 1)
    if scs_comm_result != COMM_SUCCESS:
        print(f"Communication Error: {packetHandler.getTxRxResult(scs_comm_result)}")
    elif scs_error != 0:
        print(f"Servo Error: {packetHandler.getRxPacketError(scs_error)}")
    else:
        print(f"Torque enabled for servo ID: {scs_id}")

# Function to disable torque
def torque_disable(scs_id):
    scs_comm_result, scs_error = packetHandler.TorqueDisable(scs_id)
    if scs_comm_result != COMM_SUCCESS:
        print(f"Communication Error: {packetHandler.getTxRxResult(scs_comm_result)}")
    elif scs_error != 0:
        print(f"Servo Error: {packetHandler.getRxPacketError(scs_error)}")
    else:
        print(f"Torque disabled for servo ID: {scs_id}")

# Example usage
if __name__ == "__main__":
    torque_enable(SCS_ID)
    # Add any other operations you want to perform while torque is enabled
    # torque_disable(SCS_ID)

    # Close the port when done
    portHandler.closePort()
