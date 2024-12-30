import serial
import struct
import crcmod
import time
import logging
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

# Configure a logger for geat pump
gearpump_logger = logging.getLogger('GearPump')
gearpump_handler = logging.FileHandler('gearpump.log')
gearpump_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
gearpump_logger.addHandler(gearpump_handler)
gearpump_logger.setLevel(logging.INFO)

class GearPump:
    def 
