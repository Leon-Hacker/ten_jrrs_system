import pandas as pd
import numpy as np
from PySide6.QtCore import QThread, Signal, QObject

class ReactorScheduler:
    def __init__(self, num_reactors, interval, max_power):
        self.num_reactors = num_reactors
        self.max_power = max_power  # Maximum available power
        self.reactor_minutes = [0 for _ in range(num_reactors)]  # Track reactor time in minutes
        self.current_index = 0
        self.interval = interval  # Set the interval dynamically
        self.running_reactors = []  # Store the number of running reactors for each interval
        self.total_energy_consumed = 0  # Total energy consumed by reactors
    
    def get_operational_reactors(self, available_power):
        """ Adjust the number of reactors to run based on the available power percentage. """
        if available_power < 10:
            return 0
        elif available_power < 20:
            return 1
        elif available_power < 30:
            return 2
        elif available_power < 40:
            return 3
        elif available_power < 50:
            return 4
        elif available_power < 60:
            return 5
        elif available_power < 70:
            return 6
        elif available_power < 80:
            return 7
        elif available_power < 90:
            return 8
        elif available_power < 100:
            return 9
        else:
            return 10
    
    def update_reactor_minutes(self, num_active_reactors):
        reactor_power_consumption = 0.1 * self.max_power  # Power consumption per reactor
        energy_consumed = num_active_reactors * reactor_power_consumption * (self.interval / 60)
        self.total_energy_consumed += energy_consumed  # Add energy consumed

        for i in range(num_active_reactors):
            reactor_index = (self.current_index + i) % self.num_reactors
            self.reactor_minutes[reactor_index] += self.interval  # Increment minutes
        self.current_index = (self.current_index + num_active_reactors) % self.num_reactors
        self.running_reactors.append(num_active_reactors)  # Track number of reactors

    def schedule_reactors(self, power_readings):
        """ Schedule reactors based on available power """
        for available_power in power_readings:
            num_active_reactors = self.get_operational_reactors(available_power)
            self.update_reactor_minutes(num_active_reactors)

    def calculate_efficiency(self, total_solar_power):
        if total_solar_power == 0:
            return 0
        efficiency = self.total_energy_consumed / total_solar_power
        return efficiency


class InterOpWorker(QObject):
    solar_data_signal = Signal(float)  # Signal to update solar power in GUI
    reactor_state_signal = Signal(list)  
    efficiency_signal = Signal(float)  # Signal to output the best efficiency
    solar_reactor_signal = Signal(float, list)
    finished = Signal()  # Signal to indicate when processing is finished

    def __init__(self, interval_minutes, csv_file):
        super().__init__()
        self.interval = interval_minutes
        self.solar_data, self.max_power = self.load_solar_data(csv_file, interval_minutes)

        x_values = np.linspace(1.0, 2.0, 50)  # Test values of x
        self.best_x, self.best_efficiency = self.find_best_x(x_values, interval_minutes)
        print(self.best_x)

        self.scheduler = ReactorScheduler(10, interval_minutes, self.max_power / self.best_x)
        self.running = True

        self.normalized_power = (self.solar_data / (self.max_power / self.best_x)) * 100
        self.reactor_states = [False for _ in range(10)]  # Initialize reactor states

    def load_solar_data(self, filepath, interval_minutes):
        data = pd.read_csv(filepath)
        data['TIMESTAMP'] = pd.to_datetime(data['TIMESTAMP'])
        data.set_index('TIMESTAMP', inplace=True)
        resampled_data = data.resample(f'{interval_minutes}min').mean()
        resampled_data.reset_index(inplace=True)
        max_power = resampled_data['InvPDC_kW_Avg'].max()
        return resampled_data['InvPDC_kW_Avg'], max_power

    def calculate_efficiency_for_x(self, x, interval_minutes):
        max_power = self.max_power / x
        power_percentages = (self.solar_data / max_power) * 100

        scheduler = ReactorScheduler(10, interval_minutes, max_power)
        scheduler.schedule_reactors(power_percentages)

        total_solar_power_generated = self.solar_data.sum() * (interval_minutes / 60)  # Convert to kWh
        efficiency = scheduler.calculate_efficiency(total_solar_power_generated)
        return efficiency

    def find_best_x(self, x_values, interval_minutes):
        best_efficiency = 0
        best_x = None
        for x in x_values:
            efficiency = self.calculate_efficiency_for_x(x, interval_minutes)
            if efficiency > best_efficiency:
                best_efficiency = efficiency
                best_x = x
        return best_x, best_efficiency

    def run(self):
        self.efficiency_signal.emit(self.best_efficiency)
        index = 0
        check_interval_ms = 500
        total_wait_time = 0

        while self.running:
            if index >= len(self.solar_data):
                self.running = False
                break

            if total_wait_time >= self.interval * 60000:
                available_power = self.normalized_power.iloc[index]
                self.adjust_reactors(available_power)
                self.solar_reactor_signal.emit(available_power, self.reactor_states)
                index += 1
                total_wait_time = 0

            QThread.msleep(check_interval_ms)
            total_wait_time += check_interval_ms

        self.finished.emit()

    def adjust_reactors(self, available_power):
        num_reactors_to_run = self.scheduler.get_operational_reactors(available_power)

        reactors_to_activate = []
        reactors_to_deactivate = []
        shared = 0

        for i in range(self.scheduler.num_reactors):
            reactor_index = (self.scheduler.current_index + i) % self.scheduler.num_reactors
            if (len(reactors_to_activate) + shared) < num_reactors_to_run:
                if self.reactor_states[reactor_index]:
                    shared += 1
                else:
                    reactors_to_activate.append(reactor_index)
            elif (len(reactors_to_activate) + shared) >= num_reactors_to_run and self.reactor_states[reactor_index]:
                reactors_to_deactivate.append(reactor_index)

        for reactor_index in reactors_to_activate:
            self.reactor_states[reactor_index] = True

        for reactor_index in reactors_to_deactivate:
            self.reactor_states[reactor_index] = False

        self.scheduler.current_index = (self.scheduler.current_index + num_reactors_to_run) % self.scheduler.num_reactors

    def stop(self):
        self.running = False
