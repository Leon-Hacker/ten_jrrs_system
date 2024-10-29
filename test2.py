# main.py or your main file
import sys
import pyqtgraph as pg
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton
from PySide6.QtCore import QThread, QTimer
from intermittent_operation_dialog import IntermittentOperationDialog  # Import the dialog
from inter_oper import InterOpWorker  # Assuming this is your worker file

class TestIntermittentOperation(QMainWindow):
    def __init__(self, interval_minutes, csv_file):
        super().__init__()

        self.setWindowTitle("Real-time Plot: Available Power and Number of Running Reactors")
        self.setGeometry(100, 100, 800, 600)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout()
        self.central_widget.setLayout(self.layout)

        # Show dialog button
        self.show_dialog_button = QPushButton("Show Intermittent Operation Dialog", self)
        self.show_dialog_button.clicked.connect(self.open_intermittent_dialog)
        self.layout.addWidget(self.show_dialog_button)

        # Initialize data for plots
        self.dc_power_data = []
        self.reactor_data = []
        self.time_data = []

        # Initialize the worker and move it to a new thread
        self.worker = InterOpWorker(interval_minutes, csv_file)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)

        # Connect signals
        self.worker.solar_reactor_signal.connect(self.update_real_time_plots)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)  # Clean up the thread

        # Start the worker thread and the run process
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()

        # Timer for periodic plot updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_dialog_plots)
        self.timer.start(500)

        # Initialize the dialog (but don’t show it yet)
        self.inter_op_dialog = IntermittentOperationDialog(interval_minutes)

    def open_intermittent_dialog(self):
        """Show the intermittent operation dialog."""
        self.inter_op_dialog.show()

    def update_real_time_plots(self, available_power, reactor_states):
        """Receive real-time updates from InterOpWorker and store them for plotting."""
        running_reactors = len(reactor_states)  # Count reactors currently running (assuming True indicates active)
        self.dc_power_data.append(available_power)
        self.reactor_data.append(running_reactors)
        self.time_data.append(len(self.time_data))

    def update_dialog_plots(self):
        """Update plots in the dialog with the latest data."""
        if self.inter_op_dialog.isVisible():  # Only update if the dialog is open
            self.inter_op_dialog.update_plots(self.time_data, self.dc_power_data, self.reactor_data)

    def closeEvent(self, event):
        """Handle the window close event to stop the worker and clean up the thread."""
        self.worker.stop()
        self.worker_thread.quit()
        self.worker_thread.wait()
        event.accept()

# Program entry point
if __name__ == "__main__":
    app = QApplication(sys.argv)
    interval_minutes = 60
    csv_file = "onemin-Ground-2017-06-04.csv"
    window = TestIntermittentOperation(interval_minutes, csv_file)
    window.show()
    sys.exit(app.exec())
