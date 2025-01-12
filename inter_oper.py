import pandas as pd
import numpy as np
from PySide6.QtCore import QThread, Signal, QObject, QMutex, QElapsedTimer, QMutexLocker, QCoreApplication

class ReactorScheduler:
    def __init__(self, num_reactors, interval, max_power):
        self.num_reactors = num_reactors
        self.max_power = max_power  # Maximum available power
        self.reactor_minutes = [0 for _ in range(num_reactors)]  # Track reactor time in minutes
        self.interval = interval  # Set the interval dynamically
        self.running_reactors = set()  # Track currently active reactors by their indices
        self.total_energy_consumed = 0  # Total energy consumed by reactors
        self.running_reactors_his = [] # Store the number of running reactors for each interval
        self.relays_to_oc = None  # Track the relays to open/close
    
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

        # Sort reactors by runtime, so we activate those with the least runtime
        reactors_by_runtime = sorted(range(self.num_reactors), key=lambda x: self.reactor_minutes[x])
        
        # Determine currently required reactors and adjust activations based on runtime priority
        if num_active_reactors < len(self.running_reactors):
            # Deactivate reactors with the most runtime first
            excess_reactors = sorted(self.running_reactors, key=lambda x: -self.reactor_minutes[x])
            for reactor_index in excess_reactors[:len(self.running_reactors) - num_active_reactors]:
                self.running_reactors.remove(reactor_index)
        
        elif num_active_reactors > len(self.running_reactors):
            # Activate reactors with the least runtime first
            for reactor_index in reactors_by_runtime:
                if len(self.running_reactors) < num_active_reactors:
                    self.running_reactors.add(reactor_index)

        # Update runtime for active reactors
        for reactor_index in self.running_reactors:
            self.reactor_minutes[reactor_index] += self.interval
        
        self.running_reactors_his.append(num_active_reactors)  # Track the number of running reactors for plotting

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
    
    def print_runtime_distribution(self):
        """ Optional: Print runtime distribution for debugging or analysis """
        print("Reactor Runtime Distribution:", self.reactor_minutes)
    
    def schedule_reactors_v2(self, power_readings):
        """ Schedule reactors based on available power """
        for available_power in power_readings:
            num_active_reactors = self.get_operational_reactors(available_power)
            self.update_reactor_minutes_v2(num_active_reactors)
        return num_active_reactors

    def update_reactor_minutes_v2(self, num_active_reactors):
        reactor_power_consumption = 0.1 * self.max_power  # Power consumption per reactor
        energy_consumed = num_active_reactors * reactor_power_consumption * (self.interval / 60)
        self.total_energy_consumed += energy_consumed  # Add energy consumed
        self.relays_to_oc = [0 for _ in range(16)]

        # Sort reactors by runtime, so we activate those with the least runtime
        reactors_by_runtime = sorted(range(self.num_reactors), key=lambda x: self.reactor_minutes[x])
        
        # Determine currently required reactors and adjust activations based on runtime priority
        if num_active_reactors < len(self.running_reactors):
            # Deactivate reactors with the most runtime first
            excess_reactors = sorted(self.running_reactors, key=lambda x: -self.reactor_minutes[x])
            for reactor_index in excess_reactors[:len(self.running_reactors) - num_active_reactors]:
                self.running_reactors.remove(reactor_index)
        
        elif num_active_reactors > len(self.running_reactors):
            # Activate reactors with the least runtime first
            for reactor_index in reactors_by_runtime:
                if len(self.running_reactors) < num_active_reactors:
                    self.running_reactors.add(reactor_index)

        # Update runtime for active reactors
        for reactor_index in self.running_reactors:
            self.reactor_minutes[reactor_index] += self.interval
            self.relays_to_oc[reactor_index] = 1
        
        self.running_reactors_his.append(num_active_reactors)

class InterOpWorker(QObject):
    solar_data_signal = Signal(float)  # Signal to update solar power in GUI
    reactor_state_signal = Signal(list)  
    efficiency_signal = Signal(float)  # Signal to output the best efficiency
    solar_reactor_signal = Signal(float, list)
    finished = Signal()  # Signal to indicate when processing is finished
    stopped_signal = Signal()  # Signal to indicate when processing is stopped
    reset_signal = Signal()  # Signal to indicate when processing is reset

    def __init__(self, interval_minutes, csv_file, relay_control_worker, servo_control_worker, gearpump_worker, ps_worker):
        super().__init__()
        self.relay_control_worker = relay_control_worker
        self.servo_control_worker = servo_control_worker
        self.gearpump_worker = gearpump_worker
        self.ps_worker = ps_worker
        self.mutex = QMutex()
        self.interval = interval_minutes
        self.solar_data, self.max_power = self.load_solar_data(csv_file, interval_minutes)

        x_values = np.linspace(1.0, 2.0, 50)  # Test values of x
        self.best_x, self.best_efficiency = self.find_best_x(x_values, interval_minutes)
        print(self.best_x, self.best_efficiency)

        # Initialize ReactorScheduler with the best max power and interval
        self.scheduler = ReactorScheduler(10, interval_minutes, self.max_power / self.best_x)
        self.running = True

        # Normalize the solar data for power percentages
        self.normalized_power = (self.solar_data / (self.max_power / self.best_x)) * 100

        self.relay_state_received = [0 for _ in range(16)]  # Track the relay state received

    def load_solar_data(self, filepath, interval_minutes):
        """Loads and resamples solar data from a CSV file."""
        data = pd.read_csv(filepath)
        data['TIMESTAMP'] = pd.to_datetime(data['TIMESTAMP'])
        data.set_index('TIMESTAMP', inplace=True)
        resampled_data = data.resample(f'{interval_minutes}min').mean()
        resampled_data.reset_index(inplace=True)
        max_power = resampled_data['InvPDC_kW_Avg'].max()
        return resampled_data['InvPDC_kW_Avg'], max_power

    def calculate_efficiency_for_x(self, x, interval_minutes):
        """Calculates efficiency for a given x value by adjusting the max power."""
        max_power = self.max_power / x
        power_percentages = (self.solar_data / max_power) * 100

        scheduler = ReactorScheduler(10, interval_minutes, max_power)
        scheduler.schedule_reactors(power_percentages)

        total_solar_power_generated = self.solar_data.sum() * (interval_minutes / 60)  # Convert to kWh
        efficiency = scheduler.calculate_efficiency(total_solar_power_generated)
        return efficiency

    def find_best_x(self, x_values, interval_minutes):
        """Finds the best x value that maximizes efficiency."""
        best_efficiency = 0
        best_x = None
        for x in x_values:
            efficiency = self.calculate_efficiency_for_x(x, interval_minutes)
            if efficiency > best_efficiency:
                best_efficiency = efficiency
                best_x = x
        return best_x, best_efficiency

    def run(self):
        """Main execution loop for managing reactor scheduling based on solar data."""
        index = 0
        check_interval_ms = 500  # Polling interval in milliseconds
        # interval_ms = self.interval * 60 * 1000  # Convert interval to milliseconds
        interval_ms = 60*1000

        start_time = QElapsedTimer()
        start_time.start()  # Start the timer at the beginning of the loop
        next_run_time = start_time.elapsed() #+ interval_ms  # Target time for the next interval

        while self.running:
            if index >= len(self.solar_data):
                self.running = False
                break

            # Check if it's time for the next interval
            if start_time.elapsed() >= next_run_time:
                # Get the current solar power and schedule reactors
                num_active_reactors_old = len(self.scheduler.running_reactors)
                available_power = self.normalized_power.iloc[index]
                print(available_power)
                num_active_reactors_new = self.scheduler.schedule_reactors_v2([available_power])  # Schedule reactors for current power level
                print(num_active_reactors_new, num_active_reactors_old)

                # Adjust activations of reactors based on the available power
                if num_active_reactors_new < num_active_reactors_old:
                    """Close reactors that are not needed: 1. set relay state, 2. set power supply voltage, 3. set gear pump rotate rate, 4. close servo motor, 5. disable torque"""
                    # Ensure relay state is correct before proceeding
                    self.relay_control_worker.button_checked.emit(
                        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
                        self.scheduler.relays_to_oc
                    )
                    i = 0
                    while True:
                        with QMutexLocker(self.mutex):
                            if self.relay_state_received == self.scheduler.relays_to_oc:
                                break
                        if i > 1:
                            print(f"[Close reacotrs][relay]Checking {i} times")
                        i += 1
                        QThread.msleep(500)
                    
                    # Set the maximum voltage for the power supply
                    target_voltage = self.get_ps_voltage(num_active_reactors_new)
                    self.ps_worker.button_checked.emit(target_voltage)
                    i = 0
                    while True:
                        with QMutexLocker(self.mutex):
                            if self.ps_worker.voltage_set == target_voltage:
                                break
                        if i > 1:
                            print(f"[Close reacotrs][ps]Checking {i} times")
                        i += 1
                        QThread.msleep(500)

                    # Adjust the rotate rate of the gear pump
                    target_rotate_rate = self.get_gearpump_rotate_rate(num_active_reactors_new)
                    self.gearpump_worker.button_checked.emit(target_rotate_rate)
                    i = 0
                    while True:
                        with QMutexLocker(self.mutex):
                            if abs(self.gearpump_worker.cur_rotate_rate - target_rotate_rate) < 10:
                                break
                        if i > 1:
                            print(f"[Close reacotrs][gearpump]Checking {i} times")
                        i += 1
                        QThread.msleep(500)

                    # Ensure servo motor is closed before proceeding
                    reactors_to_close = {id_r for id_r in range(10) if id_r not in self.scheduler.running_reactors}
                    reactors_to_distorque = reactors_to_close.copy()

                    for id_r in reactors_to_close:
                        self.servo_control_worker.button_checked_close.emit(id_r + 1)

                    i = 0
                    while reactors_to_close:
                        with QMutexLocker(self.mutex):
                            reactors_to_close = {id_r for id_r in reactors_to_close if self.servo_control_worker.servos_pos[id_r + 1] < 2900}
                        if i > 10:
                            print(f"[Close reacotrs][servo]Checking {i} times")
                        i += 1
                        QThread.msleep(500)

                    # Disable torque of reactor to be closed
                    for id_r in reactors_to_distorque:
                        self.servo_control_worker.button_checked_distorque.emit(id_r + 1)

                    i = 0
                    while reactors_to_distorque:
                        with QMutexLocker(self.mutex):
                            reactors_to_distorque = {id_r for id_r in reactors_to_distorque if self.servo_control_worker.servos_load[id_r + 1] != 0}
                        if i > 1:
                            print(f"[Close reacotrs][distorque]Checking {i} times")
                        i += 1
                        QThread.msleep(500)

                elif num_active_reactors_new > num_active_reactors_old:
                    """ Open reactors that are needed: 1. open servo motor, 2. set gear pump rotate rate, 3. disable torque, 4. set power supply voltage, 5. set relay state"""
                    # Ensure servo motor is opened before proceeding
                    reactors_to_open = self.scheduler.running_reactors.copy()
                    reactors_to_distorque = reactors_to_open.copy()

                    for idx_r in reactors_to_open:
                        self.servo_control_worker.button_checked_open.emit(idx_r + 1)

                    i = 0
                    while reactors_to_open:
                        with QMutexLocker(self.mutex):
                            reactors_to_open = {id_r for id_r in reactors_to_open if self.servo_control_worker.servos_pos[id_r + 1] > 2200}
                        if i > 10:
                            print(f"[Open reacotrs][servo]Checking {i} times")
                        i += 1
                        QThread.msleep(500)

                    # Adjust the rotate rate of the gear pump
                    target_rotate_rate = self.get_gearpump_rotate_rate(num_active_reactors_new)
                    self.gearpump_worker.button_checked.emit(target_rotate_rate)
                    i = 0
                    while True:
                        with QMutexLocker(self.mutex):
                            if abs(self.gearpump_worker.cur_rotate_rate - target_rotate_rate) < 10:
                                break
                        if i > 1:
                            print(f"[Open reacotrs][gearpump]Checking {i} times")
                        i += 1
                        QThread.msleep(1500)
                    
                    # Disable torque of reactor to be opened
                    for id_r in reactors_to_distorque:
                        self.servo_control_worker.button_checked_distorque.emit(id_r + 1)
                    
                    i = 0
                    while reactors_to_distorque:
                        with QMutexLocker(self.mutex):
                            reactors_to_distorque = {id_r for id_r in reactors_to_distorque if self.servo_control_worker.servos_load[id_r + 1] != 0}
                        if i > 1:
                            print(f"[Open reacotrs][distorque]Checking {i} times")
                        i += 1
                        QThread.msleep(500)

                    # Set the maximum voltage for the power supply
                    target_voltage = self.get_ps_voltage(num_active_reactors_new)
                    self.ps_worker.button_checked.emit(target_voltage)
                    i = 0
                    while True:
                        with QMutexLocker(self.mutex):
                            if self.ps_worker.voltage_set == target_voltage:
                                break
                        if i > 1:
                            print(f"[Open reacotrs][ps]Checking {i} times")
                        i += 1
                        QThread.msleep(500)

                    # Ensure relay state is correct before proceeding
                    self.relay_control_worker.button_checked.emit(
                        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
                        self.scheduler.relays_to_oc
                    )
                    i = 0
                    while True:
                        with QMutexLocker(self.mutex):
                            if self.relay_state_received == self.scheduler.relays_to_oc:
                                break
                        if i > 1:
                            print(f"[Open reacotrs][relay]Checking {i} times")
                        i += 1
                        QThread.msleep(500)

                # Emit signals to update GUI with solar power and reactor states
                self.solar_reactor_signal.emit(available_power, list(self.scheduler.running_reactors))

                # Move to the next index and update the target time for the next interval
                index += 1
                next_run_time += interval_ms

            # Sleep for the check interval to avoid busy-waiting
            QThread.msleep(check_interval_ms)
        self.scheduler.print_runtime_distribution()
        self.finished.emit()

    def reset(self):
        """Resets the worker state for a new run."""
        self.running = True
        self.scheduler = ReactorScheduler(10, self.interval, self.max_power / self.best_x)

    def stop(self):
        """Stops the execution loop."""
        self.running = False
    
    def receive_relay_state(self, relay_state):
        """Receives the relay state from the relay control worker."""
        with QMutexLocker(self.mutex):
            self.relay_state_received = relay_state

    def get_gearpump_rotate_rate(self, num_active_reactors):
        """Get the rotate rate of the gear pump."""
        rotate_rates = {0: 0, 1: 1340, 2: 1452, 3: 1588, 4: 1753, 5: 1860, 6: 2000, 7: 2190, 8: 2320, 9: 2484, 10: 2600}
        return rotate_rates[num_active_reactors]
    
    def get_ps_voltage(self, num_active_reactors):
        """Get the voltage of the power supply."""
        voltages = {0: 0, 1: 10, 2: 20, 3: 30, 4: 40, 5: 50, 6: 60, 7: 70, 8: 80, 9: 90, 10: 100}
        return voltages[num_active_reactors]