from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
import sys
import time

class Worker(QObject):
    task_done = Signal()  # Signal to emit when the task is done
    long = Signal()
    quick = Signal()

    @Slot()
    def long_task(self):
        """Simulate a long task in the worker thread."""
        time.sleep(1)  # This blocks the execution of this method only
        print("Worker started long task...")
        time.sleep(10)  # This blocks the execution of this method only
        print("Worker finished long task")
        self.task_done.emit()  # Notify that the task is done

    @Slot()
    def quick_task(self):
        """Quick task to show that the worker's event loop is still running."""
        print("Quick task executed in worker thread!")

class MainController(QWidget):
    def __init__(self):
        super().__init__()
        self.label = QLabel("Task Status: [ ]")
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)

        # Buttons to trigger tasks
        self.long_task_button = QPushButton("Start Long Task")
        self.quick_task_button = QPushButton("Trigger Quick Task in Worker")
        self.layout.addWidget(self.long_task_button)
        self.layout.addWidget(self.quick_task_button)

        # Worker and thread setup
        self.thread = QThread()
        self.worker = Worker()
        self.worker.moveToThread(self.thread)

        # Signal-slot connections
        self.worker.long.connect(self.worker.long_task)
        self.worker.quick.connect(self.worker.quick_task)
        #self.thread.started.connect(self.start_long_task)
        self.long_task_button.clicked.connect(self.worker.long_task)
        self.quick_task_button.clicked.connect(self.worker.quick_task)

        self.worker.task_done.connect(self.update_status)

        # Start the worker thread's event loop
        self.thread.start()

    def start_long_task(self):
        """Start the long task in the worker thread."""
        self.worker.long.emit()  
    def trigger_quick_task(self):
        """Trigger a quick task in the worker thread."""
        self.worker.quick_task()  

    def update_status(self):
        """Update the status when the task is done."""
        self.label.setText("Task Status: [Task Finished]")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainController()
    window.show()
    sys.exit(app.exec())