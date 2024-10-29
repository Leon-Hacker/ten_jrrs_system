from PySide6.QtCore import QCoreApplication, QObject, QThread, QMutex, QWaitCondition, Signal, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget
import sys

class Worker(QObject):
    finished = Signal()  # Signal emitted when work is finished
    status_update = Signal(str)  # Signal to update the status label
    
    def __init__(self):
        super().__init__()
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self.ready = False  # Condition variable to check if worker can proceed

    def run(self):

        while True:
            print("1")
            self.status_update.emit("Worker: Waiting for signal to continue...")
            print("Worker: Starting task and waiting for the signal to continue...")
            
            # Lock the mutex and wait until the condition is met
            while not self.ready:  # Wait until 'ready' is True
                QThread.msleep(10000)  # Sleep for 100 ms
                QCoreApplication.processEvents()  # Process events to prevent GUI freeze
            
            # Continue with the rest of the task
            self.status_update.emit("Worker: Signal received! Resuming task.")
            print("Worker: Signal received! Resuming task.")
            self.ready = False  # Reset the condition


    def allow_continue(self):
        """Set the condition to True and wake the thread."""
        self.ready = True
        

class Controller(QWidget):
    # Signal to allow the worker to continue
    allow_continue_signal = Signal()

    def __init__(self):
        super().__init__()

        # UI Setup
        self.setWindowTitle("QWaitCondition Example")
        self.layout = QVBoxLayout(self)
        
        self.label = QLabel("Press 'Start Worker' to begin.")
        self.start_button = QPushButton("Start Worker")
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.start_button)
        self.send_signal_button = QPushButton("Send Signal to Worker")
        self.layout.addWidget(self.send_signal_button)
        
        # Worker setup
        self.worker = Worker()
        self.worker_thread = QThread()

        # Move the worker to its own thread
        self.worker.moveToThread(self.worker_thread)

        # Connect signals and slots
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.worker_thread.quit)
        self.allow_continue_signal.connect(self.worker.allow_continue)
        self.send_signal_button.clicked.connect(self.send_signal)
        self.worker.status_update.connect(self.update_label)  # Update label from worker

        # Button click to start the worker and set a timer to emit the allow_continue_signal
        self.start_button.clicked.connect(self.start_worker)

    def start_worker(self):
        self.worker_thread.start()


    def send_signal(self):
        self.allow_continue_signal.emit()  # Emit the signal to continue
        print("Controller: Emitting signal to allow the worker to continue...")

    def update_label(self, text):
        """Update the label text based on worker status."""
        self.label.setText(text)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    controller = Controller()
    controller.show()
    sys.exit(app.exec())
