# intermittent_operation_dialog.py
import pyqtgraph as pg
from PySide6.QtWidgets import QDialog, QVBoxLayout

class IntermittentOperationDialog(QDialog):
    def __init__(self, interval_minutes):
        super().__init__()

        self.setWindowTitle("Intermittent Operation: Real-time Plot")
        self.setGeometry(200, 200, 800, 600)

        # Create layout and add plot widgets
        layout = QVBoxLayout()

        self.plot_widget_power = pg.PlotWidget(title=f"Available Power (%) every {interval_minutes} minutes")
        self.plot_widget_reactors = pg.PlotWidget(title="Number of Running Reactors")

        layout.addWidget(self.plot_widget_power)
        layout.addWidget(self.plot_widget_reactors)
        self.setLayout(layout)

        # Initialize curves for updating plots
        self.power_curve = self.plot_widget_power.plot(pen="b")
        self.reactor_curve = self.plot_widget_reactors.plot(pen="r")

    def update_plots(self, time_data, dc_power_data, reactor_data):
        """Update the plot data in the dialog."""
        self.power_curve.setData(time_data, dc_power_data)
        self.reactor_curve.setData(time_data, reactor_data)
