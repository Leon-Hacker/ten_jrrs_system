from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication

class Worker(QObject):
    timeout_signal = Signal()

    def __init__(self):
        super().__init__()
        self.timer = QTimer()
        self.timer.setInterval(1000)  # Set interval to 1 second
        self.timer.timeout.connect(self.on_timeout)

    def start(self):
        self.timer.start()  # Start the timer

    def stop(self):
        self.timer.stop()  # Stop the timer

    def on_timeout(self):
        print("Timer timed out!")
        self.timeout_signal.emit()  # Emit a custom signal on timeout

app = QApplication([])

# Create and move the worker to a separate thread
worker = Worker()
thread = QThread()
worker.moveToThread(thread)

# Connect signals to start and stop the timer in the correct thread
thread.started.connect(worker.start)
app.aboutToQuit.connect(worker.stop)  # Ensure the timer stops on app quit
thread.start()

app.exec()
