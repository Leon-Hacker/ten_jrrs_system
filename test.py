import sys
import pyqtgraph as pg
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtCore import QThread, QTimer
import matplotlib.pyplot as plt
from intermittent_operation import InterOpWorker

class TestIntermittentOperation(QMainWindow):
    def __init__(self, interval_minutes, csv_file):
        super().__init__()

        self.setWindowTitle("Real-time Plot: Available Power and Number of Running Reactors")
        self.setGeometry(100, 100, 800, 600)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout()
        self.central_widget.setLayout(self.layout)

        self.plot_widget_power = pg.PlotWidget(title=f"Available Power (%) every {interval_minutes} minutes")
        self.plot_widget_reactors = pg.PlotWidget(title="Number of Running Reactors")
        self.layout.addWidget(self.plot_widget_power)
        self.layout.addWidget(self.plot_widget_reactors)

        self.power_curve = self.plot_widget_power.plot(pen="b")
        self.reactor_curve = self.plot_widget_reactors.plot(pen="r")

        self.dc_power_data = []
        self.reactor_data = []
        self.time_data = []

        # Initialize the worker and move to a new thread
        self.worker = InterOpWorker(interval_minutes, csv_file)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)

        # Connect signals
        self.worker.solar_reactor_signal.connect(self.update_real_time_plots)
        self.worker.finished.connect(self.plot_final_summary)  # Connect finished to plot_final_summary
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)  # Clean up the thread

        # Start the worker thread and the run process
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()

        # Timer for periodic plot updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(500)

    def update_real_time_plots(self, available_power, reactor_states):
        running_reactors = sum(reactor_states)
        self.dc_power_data.append(available_power)
        self.reactor_data.append(running_reactors)
        self.time_data.append(len(self.time_data))

    def update_plot(self):
        if len(self.time_data) == len(self.dc_power_data):
            self.power_curve.setData(self.time_data, self.dc_power_data)
        if len(self.time_data) == len(self.reactor_data):
            self.reactor_curve.setData(self.time_data, self.reactor_data)

    def plot_final_summary(self):
        plt.figure(figsize=(10, 6))
        plt.subplot(2, 1, 1)
        plt.plot(self.time_data, self.dc_power_data, label='Available Power (%)', color='blue')
        plt.xlabel('Time (Steps)')
        plt.ylabel('Available Power (%)')
        plt.title(f"DC Power Averaged Every {self.worker.interval} Minutes")
        plt.grid(True)

        plt.subplot(2, 1, 2)
        plt.plot(self.time_data, self.reactor_data, label='Running Reactors', color='red')
        plt.xlabel('Time (Steps)')
        plt.ylabel('Number of Running Reactors')
        plt.title(f"Number of Running Reactors Averaged Every {self.worker.interval} Minutes")
        plt.grid(True)

        plt.tight_layout()
        plt.show()

    def closeEvent(self, event):
        self.worker.stop()
        self.worker_thread.quit()
        self.worker_thread.wait()
        event.accept()

# Test program entry point
if __name__ == "__main__":
    app = QApplication(sys.argv)
    interval_minutes = 20
    csv_file = "onemin-Ground-2017-06-04.csv"
    window = TestIntermittentOperation(interval_minutes, csv_file)
    window.show()
    sys.exit(app.exec())
