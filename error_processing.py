# 1. Prevent the voltage of any single reactor from exceeding the limit (28 V)
# If the voltage of any single reactor exceeds the limit, the power supply is turned off and the maximum voltage of the power supply is set to 0 V
# 2. Prevent the outlet pressure of the gear pump from exceeding the limit (5.5 bar)
# If the outlet pressure of the gear pump exceeds the limit, the gear pump is turned off and the power supply is turned off
from PySide6.QtCore import QThread, Signal, QObject, QMutex, QTimer, QMutexLocker, QCoreApplication
import logging
from logging.handlers import RotatingFileHandler

# Configure a logger for the error processing with a rotating file handler
error_processing_logger = logging.getLogger('error_processing')
error_processing_handler = RotatingFileHandler(
    'logs/error_processing.log',
    maxBytes=5*1024*1024,
    backupCount=5,
    encoding='utf-8'
)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
error_processing_handler.setFormatter(formatter)
error_processing_logger.addHandler(error_processing_handler)
error_processing_logger.setLevel(logging.INFO)

class ErrorProcessing(QObject):
    """Class for managing errors in the InterOpWorker running process."""
    stopped = Signal()

    turn_off_ps = Signal()
    turn_off_gp = Signal()

    def __init__(self):
        super().__init__()
        self.mutex = QMutex()
        self.running = True
        self.timer = None
        self.cur_voltages = [0] * 10
        self.cur_pressure = 0
    
    def stop(self):
        self.running = False

    def start_checking(self):
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.run)
        self.timer.start()
    
    def run(self):
        """Main execution loop for managing errors."""
        if not self.running:
            self.timer.stop()
            return
        # Check if the voltage of any single reactor exceeds the limit
        # self.voltage_collector_worker.cur_voltages is a list of the current voltages of the 10 reactors
        voltages = self.cur_voltages
        for index, volt in enumerate(voltages):
            if volt > 4:
                self.turn_off_ps.emit()
                error_processing_logger.info(f"Reactor {index + 1} voltage ({volt} V) exceeded limit. Turning off power supply.")
                break
    
        # Check if the outlet pressure of the gear pump exceeds the limit
        pressure = self.cur_pressure
        if pressure > 5.5:
            self.turn_off_ps.emit()
            self.turn_off_gp.emit()
            error_processing_logger.info(f"{pressure}Pressure exceeded limit. Turning off gear pump and power supply.")


    def get_reacotr_voltages(self, voltages):
        with QMutexLocker(self.mutex):
            self.cur_voltages = voltages

    def get_gp_pressure(self, pressure):
        with QMutexLocker(self.mutex):
            self.cur_pressure = pressure
                
                    
            
            
            

