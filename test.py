import sys
import pyqtgraph as pg
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtCore import QTimer
import matplotlib.pyplot as plt
from intermittent_operation import InterOpThread


class TestIntermittentOperation(QMainWindow):
    def __init__(self, interval_minutes, csv_file):
        super().__init__()

        # Set up the window
        self.setWindowTitle("Real-time Plot: Available Power and Number of Running Reactors")
        self.setGeometry(100, 100, 800, 600)

        # Create the layout for the window
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout()
        self.central_widget.setLayout(self.layout)

        # Initialize pyqtgraph plot widgets
        self.plot_widget_power = pg.PlotWidget(title=f"Available Power (%) every {interval_minutes} minutes")
        self.plot_widget_reactors = pg.PlotWidget(title="Number of Running Reactors")

        # Add the plot widgets to the layout
        self.layout.addWidget(self.plot_widget_power)
        self.layout.addWidget(self.plot_widget_reactors)

        # Set up curves for power and reactors
        self.power_curve = self.plot_widget_power.plot(pen="b")  # Blue line for Available Power
        self.reactor_curve = self.plot_widget_reactors.plot(pen="r")  # Red line for Running Reactors

        # Initialize data storage for real-time plotting
        self.dc_power_data = []
        self.reactor_data = []
        self.time_data = []

        # Initialize QThread to handle intermittent operation
        self.operation_thread = InterOpThread(interval_minutes, csv_file)
        self.operation_thread.solar_reactor_signal.connect(self.update_real_time_plots)
        self.operation_thread.finished.connect(self.plot_final_summary)

        # Timer to periodically update the plot
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(500)  # Update every 500 ms

        # Start the operation thread
        self.operation_thread.start()

    def update_real_time_plots(self, available_power, reactor_states):
        """Update the data for power and reactors."""
        running_reactors = sum(reactor_states)

        # Append power and reactor data
        self.dc_power_data.append(available_power)
        self.reactor_data.append(running_reactors)
        self.time_data.append(len(self.time_data))  # Track time by index

    def update_plot(self):
        """Update the pyqtgraph plots."""
        if len(self.time_data) == len(self.dc_power_data):
            self.power_curve.setData(self.time_data, self.dc_power_data)
        if len(self.time_data) == len(self.reactor_data):
            self.reactor_curve.setData(self.time_data, self.reactor_data)

    def plot_final_summary(self):
        """Use matplotlib to plot DC Power and Number of Running Reactors after the thread completes."""
        # Generate the final summary plot using matplotlib
        plt.figure(figsize=(10, 6))

        # Plot the averaged DC power
        plt.subplot(2, 1, 1)
        plt.plot(self.time_data, self.dc_power_data, label='Available Power (%)', color='blue')
        plt.xlabel('Time (Steps)')
        plt.ylabel('Available Power (%)')
        plt.title(f"DC Power Averaged Every {self.operation_thread.interval} Minutes")
        plt.grid(True)

        # Plot the number of running reactors
        plt.subplot(2, 1, 2)
        plt.plot(self.time_data, self.reactor_data, label='Running Reactors', color='red')
        plt.xlabel('Time (Steps)')
        plt.ylabel('Number of Running Reactors')
        plt.title(f"Number of Running Reactors Averaged Every {self.operation_thread.interval} Minutes")
        plt.grid(True)

        plt.tight_layout()
        plt.show()

    def closeEvent(self, event):
        """Ensure the thread is stopped when the window is closed."""
        self.operation_thread.stop()
        self.operation_thread.wait()
        event.accept()


# Test program entry point
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Set the interval and CSV file path (update this with the correct path)
    interval_minutes = 20
    csv_file = "onemin-Ground-2017-06-04.csv"  # Update to the correct file path

    window = TestIntermittentOperation(interval_minutes, csv_file)
    window.show()

    sys.exit(app.exec())
