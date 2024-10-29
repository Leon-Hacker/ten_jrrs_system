# intermittent_dialog.py
import pyqtgraph as pg
from PySide6.QtWidgets import QDialog, QVBoxLayout

class IntermittentOperationDialog(QDialog):
    def __init__(self, interval_minutes):
        super().__init__()

        # Setup dialog window properties
        self.setWindowTitle("Intermittent Operation: Real-time Plot")
        self.setGeometry(200, 200, 800, 600)

        # Set up the layout and plot widgets
        layout = QVBoxLayout()

        # Plot for available power
        self.plot_widget_power = pg.PlotWidget(title=f"Available Power (%) every {interval_minutes} minutes")
        self.plot_widget_power.setLabel('left', 'Available Power (%)')
        self.plot_widget_power.setLabel('bottom', 'Time (Steps)')
        self.power_curve = self.plot_widget_power.plot(pen="b")  # Blue line for power
        layout.addWidget(self.plot_widget_power)

        # Plot for number of running reactors
        self.plot_widget_reactors = pg.PlotWidget(title="Number of Running Reactors")
        self.plot_widget_reactors.setLabel('left', 'Running Reactors')
        self.plot_widget_reactors.setLabel('bottom', 'Time (Steps)')
        self.reactor_curve = self.plot_widget_reactors.plot(pen="r")  # Red line for reactors
        layout.addWidget(self.plot_widget_reactors)

        # Set the layout for the dialog
        self.setLayout(layout)

        # Data storage for plotting
        self.time_data = []
        self.dc_power_data = []
        self.reactor_data = []

    def update_plots(self, time_step, available_power, running_reactors):
        """Update the plots with new data."""
        # Append new data
        self.time_data.append(time_step)
        self.dc_power_data.append(available_power)
        self.reactor_data.append(running_reactors)

        # Update plot curves
        self.power_curve.setData(self.time_data, self.dc_power_data)
        self.reactor_curve.setData(self.time_data, self.reactor_data)
