import pandas as pd
import numpy as np
from PySide6.QtCore import Qt, QThread, Signal, QObject, QMutex, QElapsedTimer, QMutexLocker, QTimer

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

from enum import Enum, auto
import logging
from logging.handlers import RotatingFileHandler

# Configure a logger for the interop worker with a rotating file handler
interop_logger = logging.getLogger('interop_worker')
interop_handler = RotatingFileHandler(
    'logs/interop_worker.log', 
    maxBytes=5*1024*1024,
    backupCount=5,
    encoding='utf-8'
)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
interop_handler.setFormatter(formatter)
interop_logger.addHandler(interop_handler)
interop_logger.setLevel(logging.INFO)

class WorkerState(Enum):
    IDLE = auto()
    CHECK_TIME = auto()
    PROCESS_INTERVAL = auto()
    
    # States for closing reactors
    SET_RELAY_STATE_CLOSE = auto()
    WAIT_RELAY_STATE_CLOSE = auto()
    SET_POWER_SUPPLY_CLOSE = auto()
    WAIT_POWER_SUPPLY_CLOSE = auto()
    SET_GEARPUMP_RATE_CLOSE = auto()
    WAIT_GEARPUMP_RATE_CLOSE = auto()
    CLOSE_SERVO_MOTOR = auto()
    WAIT_SERVO_MOTOR_CLOSE = auto()
    DISABLE_TORQUE_CLOSE = auto()
    WAIT_DISABLE_TORQUE_CLOSE = auto()
    
    # States for opening reactors
    OPEN_SERVO_MOTOR = auto()
    WAIT_SERVO_MOTOR_OPEN = auto()
    SET_GEARPUMP_RATE_OPEN = auto()
    WAIT_GEARPUMP_RATE_OPEN = auto()
    DISABLE_TORQUE_OPEN = auto()
    WAIT_DISABLE_TORQUE_OPEN = auto()
    SET_POWER_SUPPLY_OPEN = auto()
    WAIT_POWER_SUPPLY_OPEN = auto()
    SET_RELAY_STATE_OPEN = auto()
    WAIT_RELAY_STATE_OPEN = auto()
    
    # Final state
    FINISHED = auto()

class InterOpWorker(QObject):
    solar_data_signal = Signal(float)
    reactor_state_signal = Signal(list)
    efficiency_signal = Signal(float)
    solar_reactor_signal = Signal(float, list)
    finished = Signal()
    stopped_signal = Signal()
    reset_signal = Signal()
    
    def __init__(self, interval_minutes, csv_file, relay_control_worker, servo_control_worker, gearpump_worker, ps_worker):
        super().__init__()
        self.relay_control_worker = relay_control_worker
        self.servo_control_worker = servo_control_worker
        self.gearpump_worker = gearpump_worker
        self.ps_worker = ps_worker
        self.mutex = QMutex()
        self.interval = interval_minutes
        self.index = 0
        self.running = True
        
        # Load solar data and initialize scheduler
        self.solar_data, self.max_power = self.load_solar_data(csv_file, interval_minutes)
        
        x_values = np.linspace(1.0, 2.0, 50)
        self.best_x, self.best_efficiency = self.find_best_x(x_values, interval_minutes)
        interop_logger.info(f"Best X: {self.best_x}, Best Efficiency: {self.best_efficiency}")
        print(self.best_x, self.best_efficiency)
        self.scheduler = ReactorScheduler(10, interval_minutes, self.max_power / self.best_x)
        self.normalized_power = (self.solar_data / (self.max_power / self.best_x)) * 100
        self.relay_state_received = [0 for _ in range(16)]
        
        # Initialize state machine
        self.state = WorkerState.IDLE
        self.state_timer = None
        
        # Connect signals for asynchronous events
        self.relay_control_worker.interop.connect(self.on_relay_state_changed)
        self.ps_worker.interop.connect(self.on_voltage_set)
        self.gearpump_worker.interop.connect(self.on_rotate_rate_set)
        self.servo_control_worker.inter_close.connect(self.on_servo_closed)
        self.servo_control_worker.inter_open.connect(self.on_servo_opened)
        self.servo_control_worker.tor_open.connect(self.on_torque_disabled_open)
        self.servo_control_worker.tor_close.connect(self.on_torque_disabled_close)
        self.stopped_signal.connect(self.stop)
        # Add connections for opening operations as needed
        
        # Initialize timer for interval control
        self.timer = QElapsedTimer()
        self.timer.start()

        # Initialize target_interval_ms
        #self.target_interval_ms = self.interval * 60 * 1000  # Initial interval in milliseconds
        self.target_interval_ms = 60 * 1000
    def run(self):
        """Main execution loop for managing reactor scheduling based on solar data using a state machine."""
        self.state_timer = QTimer()
        self.state_timer.setSingleShot(True)
        self.state_timer.timeout.connect(self.on_timer_timeout)
        self.running = True
        self.state = WorkerState.CHECK_TIME
        self.process_next_state()
    
    def process_next_state(self):
        """Process the current state and transition to the next state."""
        if not self.running:
            self.state = WorkerState.FINISHED
        
        state_handler = {
            WorkerState.IDLE: self.idle_state,
            WorkerState.CHECK_TIME: self.check_time_state,
            WorkerState.PROCESS_INTERVAL: self.process_interval_state,
            
            # Closing reactors
            WorkerState.SET_RELAY_STATE_CLOSE: self.set_relay_state_close,
            WorkerState.WAIT_RELAY_STATE_CLOSE: lambda: None,
            WorkerState.SET_POWER_SUPPLY_CLOSE: self.set_power_supply_close,
            WorkerState.WAIT_POWER_SUPPLY_CLOSE: lambda: None,
            WorkerState.SET_GEARPUMP_RATE_CLOSE: self.set_gearpump_rate_close,
            WorkerState.WAIT_GEARPUMP_RATE_CLOSE: lambda: None,
            WorkerState.CLOSE_SERVO_MOTOR: self.close_servo_motor,
            WorkerState.WAIT_SERVO_MOTOR_CLOSE: lambda: None,
            WorkerState.DISABLE_TORQUE_CLOSE: self.disable_torque_close,
            WorkerState.WAIT_DISABLE_TORQUE_CLOSE: lambda: None,
            
            # Opening reactors
            WorkerState.OPEN_SERVO_MOTOR: self.open_servo_motor,
            WorkerState.WAIT_SERVO_MOTOR_OPEN: lambda: None,
            WorkerState.SET_GEARPUMP_RATE_OPEN: self.set_gearpump_rate_open,
            WorkerState.WAIT_GEARPUMP_RATE_OPEN: lambda: None,
            WorkerState.DISABLE_TORQUE_OPEN: self.disable_torque_open,
            WorkerState.WAIT_DISABLE_TORQUE_OPEN: lambda: None,
            WorkerState.SET_POWER_SUPPLY_OPEN: self.set_power_supply_open,
            WorkerState.WAIT_POWER_SUPPLY_OPEN: lambda: None,
            WorkerState.SET_RELAY_STATE_OPEN: self.set_relay_state_open,
            WorkerState.WAIT_RELAY_STATE_OPEN: lambda: None,
            
            # Final state
            WorkerState.FINISHED: self.finish_worker,
        }
        
        handler = state_handler.get(self.state, self.unknown_state)
        handler()
    
    def idle_state(self):
        """Handle the IDLE state."""
        interop_logger.debug("Worker is idle.")
        # Transition to CHECK_TIME immediately
        self.state = WorkerState.CHECK_TIME
        self.process_next_state()
    
    def check_time_state(self):
        """Check if it's time to process the next interval."""
        if self.index >= len(self.solar_data):
            self.state = WorkerState.FINISHED
            self.process_next_state()
            return
        
        # Calculate elapsed time since the last interval
        elapsed = self.timer.elapsed()
        # print the time passed
        interop_logger.info(f"Time passed: {elapsed} ms")
        
        if elapsed >= self.target_interval_ms:
            self.target_interval_ms += self.interval * 60 * 1000  # Schedule next interval
            #self.target_interval_ms += 60 * 1000
            self.state = WorkerState.PROCESS_INTERVAL
            self.process_next_state()
        else:
            # Calculate remaining time and set timer
            remaining_time = self.target_interval_ms - elapsed
            interop_logger.info(f"Waiting for {remaining_time} ms until next interval.")
            self.state_timer.start(remaining_time)
    
    def process_interval_state(self):
        """Process the reactor scheduling for the current interval."""
        available_power = self.normalized_power.iloc[self.index]
        num_active_reactors_old = len(self.scheduler.running_reactors)
        num_active_reactors_new = self.scheduler.schedule_reactors_v2([available_power])
        
        interop_logger.info(f"Interval {self.index}: Available Power = {available_power}, "
                     f"Old Reactors = {num_active_reactors_old}, New Reactors = {num_active_reactors_new}")
        
        if num_active_reactors_new < num_active_reactors_old:
            self.state = WorkerState.SET_RELAY_STATE_CLOSE
        elif num_active_reactors_new > num_active_reactors_old:
            self.state = WorkerState.OPEN_SERVO_MOTOR
        else:
            # No change in reactor states
            self.solar_reactor_signal.emit(available_power, list(self.scheduler.running_reactors))
            self.index += 1
            self.state = WorkerState.CHECK_TIME
        self.process_next_state()
    
    # Closing Reactors States
    def set_relay_state_close(self):
        """Set relay state for closing reactors."""
        relays_to_close = self.scheduler.relays_to_oc
        interop_logger.debug(f"Setting relay state to close: {relays_to_close}")
        self.relay_control_worker.button_checked.emit(
            list(range(1, 17)),  # Relay IDs from 1 to 16
            relays_to_close
        )
        self.state = WorkerState.WAIT_RELAY_STATE_CLOSE

    def on_relay_state_changed(self):
        """Handle relay state change for both closing and opening reactors."""
        if self.state == WorkerState.WAIT_RELAY_STATE_CLOSE:
            self.state = WorkerState.SET_POWER_SUPPLY_CLOSE
            self.process_next_state()
        elif self.state == WorkerState.WAIT_RELAY_STATE_OPEN:
            available_power = self.normalized_power[self.index]
            self.solar_reactor_signal.emit(available_power, list(self.scheduler.running_reactors))
            self.index += 1
            self.state = WorkerState.CHECK_TIME
            self.process_next_state()

    def set_power_supply_close(self):
        """Set power supply voltage for closing reactors."""
        target_voltage = self.get_ps_voltage(len(self.scheduler.running_reactors))
        interop_logger.debug(f"Setting power supply voltage to {target_voltage} for closing reactors.")
        self.ps_worker.button_checked.emit(target_voltage)
        self.state = WorkerState.WAIT_POWER_SUPPLY_CLOSE

    def on_voltage_set(self):
        """Handle power supply voltage set."""
        if self.state == WorkerState.WAIT_POWER_SUPPLY_CLOSE:
            self.state = WorkerState.SET_GEARPUMP_RATE_CLOSE
            self.process_next_state()
        elif self.state == WorkerState.WAIT_POWER_SUPPLY_OPEN:
            self.state = WorkerState.SET_RELAY_STATE_OPEN
            self.process_next_state()

    def set_gearpump_rate_close(self):
        """Set gear pump rotate rate for closing reactors."""
        self.state = WorkerState.WAIT_GEARPUMP_RATE_CLOSE
        target_rotate_rate = self.get_gearpump_rotate_rate(len(self.scheduler.running_reactors))
        interop_logger.debug(f"Setting gear pump rotate rate to {target_rotate_rate} for closing reactors.")
        self.gearpump_worker.button_checked.emit(target_rotate_rate)
        

    def on_rotate_rate_set(self):
        """Handle gear pump rotate rate set."""
        if self.state == WorkerState.WAIT_GEARPUMP_RATE_CLOSE:
            self.state = WorkerState.CLOSE_SERVO_MOTOR
            self.process_next_state()
        elif self.state == WorkerState.WAIT_GEARPUMP_RATE_OPEN:
            self.state = WorkerState.DISABLE_TORQUE_OPEN
            self.process_next_state()

    def close_servo_motor(self):
        """Close the servo motor for reactors to be closed."""
        reactors_to_close = {id_r for id_r in range(10) if id_r not in self.scheduler.running_reactors}
        self.reactors_to_close = reactors_to_close.copy()
        interop_logger.debug(f"Closing servo motors for reactors: {reactors_to_close}")
        for id_r in reactors_to_close:
            self.servo_control_worker.button_checked_close.emit(id_r + 1)
        self.state = WorkerState.WAIT_SERVO_MOTOR_CLOSE

    def on_servo_closed(self, servo_id):
        """Handle servo motor closed."""
        if self.state == WorkerState.WAIT_SERVO_MOTOR_CLOSE:
            reactor_id = servo_id - 1
            self.reactors_to_close.discard(reactor_id)
            interop_logger.debug(f"Servo motor closed for reactor {reactor_id}. Remaining to close: {self.reactors_to_close}")
            if not self.reactors_to_close:
                self.state = WorkerState.DISABLE_TORQUE_CLOSE
                self.process_next_state()

    def disable_torque_close(self):
        """Disable torque for reactors to be closed."""
        reactors_to_disable = {id_r for id_r in range(10) if id_r not in self.scheduler.running_reactors}
        self.reactors_to_distorque_close = reactors_to_disable.copy()
        interop_logger.debug(f"Disabling torque for reactors: {reactors_to_disable}")
        for id_r in reactors_to_disable:
            self.servo_control_worker.button_checked_distorque_close.emit(id_r + 1)
        self.state = WorkerState.WAIT_DISABLE_TORQUE_CLOSE

    def on_torque_disabled_close(self, servo_id):
        """Handle torque disabled."""
        if self.state == WorkerState.WAIT_DISABLE_TORQUE_CLOSE:
            reactor_id = servo_id - 1  # Adjust for 0-based indexing
            self.reactors_to_distorque_close.discard(reactor_id)
            interop_logger.debug(f"Torque disabled for reactor {reactor_id}. Remaining to disable: {self.reactors_to_distorque_close}")
            if not self.reactors_to_distorque_close:
                # Emit signals to update GUI
                available_power = self.normalized_power[self.index]
                self.solar_reactor_signal.emit(available_power, list(self.scheduler.running_reactors))
                self.index += 1
                self.state = WorkerState.CHECK_TIME
                self.process_next_state()
    
    # Opening Reactors States
    def open_servo_motor(self):
        """Open the servo motor for reactors to be opened."""
        reactors_to_open = self.scheduler.running_reactors.copy()
        self.reactors_to_open = reactors_to_open.copy()
        interop_logger.debug(f"Opening servo motors for reactors: {reactors_to_open}")
        for id_r in reactors_to_open:
            self.servo_control_worker.button_checked_open.emit(id_r + 1)
        self.state = WorkerState.WAIT_SERVO_MOTOR_OPEN

    def on_servo_opened(self, servo_id):
        """Handle servo motor opened."""
        if self.state == WorkerState.WAIT_SERVO_MOTOR_OPEN:
            reactor_id = servo_id - 1
            self.reactors_to_open.discard(reactor_id)
            interop_logger.debug(f"Servo motor opened for reactor {reactor_id}. Remaining to open: {self.reactors_to_open}")
            if not self.reactors_to_open:
                self.state = WorkerState.SET_GEARPUMP_RATE_OPEN
                self.process_next_state()

    def set_gearpump_rate_open(self):
        """Set gear pump rotate rate for opening reactors."""
        target_rotate_rate = self.get_gearpump_rotate_rate(len(self.scheduler.running_reactors))
        interop_logger.debug(f"Setting gear pump rotate rate to {target_rotate_rate} for opening reactors.")
        self.gearpump_worker.button_checked.emit(target_rotate_rate)
        self.state = WorkerState.WAIT_GEARPUMP_RATE_OPEN

    def disable_torque_open(self):
        """Disable torque for reactors to be opened."""
        reactors_to_disable = self.scheduler.running_reactors.copy()
        self.reactors_to_distorque_open = reactors_to_disable.copy()
        interop_logger.debug(f"Disabling torque for reactors: {reactors_to_disable}")
        for id_r in reactors_to_disable:
            self.servo_control_worker.button_checked_distorque_open.emit(id_r + 1)
        self.state = WorkerState.WAIT_DISABLE_TORQUE_OPEN

    def on_torque_disabled_open(self, servo_id):
        """Handle torque disabled for opening reactors."""
        if self.state == WorkerState.WAIT_DISABLE_TORQUE_OPEN:
            reactor_id = servo_id - 1 # Adjust for 0-based indexing
            self.reactors_to_distorque_open.discard(reactor_id)
            interop_logger.debug(f"Torque disabled for reactor {reactor_id}. Remaining to disable: {self.reactors_to_distorque_open}")
            if not self.reactors_to_distorque_open:
                    self.state = WorkerState.SET_POWER_SUPPLY_OPEN
                    self.process_next_state()

    def set_power_supply_open(self):
        """Set power supply voltage for opening reactors."""
        target_voltage = self.get_ps_voltage(len(self.scheduler.running_reactors))
        interop_logger.debug(f"Setting power supply voltage to {target_voltage} for opening reactors.")
        self.ps_worker.button_checked.emit(target_voltage)
        self.state = WorkerState.WAIT_POWER_SUPPLY_OPEN

    def set_relay_state_open(self):
        """Set relay state for opening reactors."""
        relays_to_open = self.scheduler.relays_to_oc
        interop_logger.debug(f"Setting relay state to open: {relays_to_open}")
        self.relay_control_worker.button_checked.emit(
            list(range(1, 17)),  # Relay IDs from 1 to 16
            relays_to_open
        )
        self.state = WorkerState.WAIT_RELAY_STATE_OPEN

    def on_timer_timeout(self):
        """Handle timer timeout to process the next state."""
        actual_elapsed = self.timer.elapsed()
        if actual_elapsed >= self.target_interval_ms:
            self.target_interval_ms += self.interval * 60 * 1000
            #self.target_interval_ms += 60 * 1000  # Schedule next interval
            interop_logger.info("Timer timeout occurred.")
            self.state = WorkerState.PROCESS_INTERVAL
            self.process_next_state()
        else:
            remaining_time = self.target_interval_ms - actual_elapsed
            interop_logger.info(f"Timer timeout occurred early. Waiting for {remaining_time} ms.")
            self.state_timer.start(remaining_time)

    def finish_worker(self):
        """Handle the FINISHED state."""
        interop_logger.info("Worker has finished processing all intervals.")
        interop_logger.info(f"{self.scheduler.reactor_minutes}")
        self.scheduler.print_runtime_distribution()
        self.finished.emit()

    def unknown_state(self):
        """Handle unknown states."""
        interop_logger.error(f"Encountered unknown state: {self.state}")
        self.finished.emit()

    def stop(self):
        """Stops the execution loop."""
        if self.state_timer.isActive():
            self.state_timer.stop()
        self.running = False
        self.state = WorkerState.FINISHED
        self.process_next_state()
    
    # Opening Reactors Signal Handlers
    # Similar to the above, implement on_torque_disabled_open, etc., as needed.
    
    # Placeholder implementations for required methods
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

    def get_gearpump_rotate_rate(self, num_active_reactors):
        """Get the rotate rate of the gear pump."""
        rotate_rates = {0: 0, 1: 1340, 2: 1452, 3: 1588, 4: 1753, 5: 1860, 6: 2000, 7: 2190, 8: 2320, 9: 2484, 10: 2600}
        #rotate_rates = {0: 0, 1: 20, 2: 40, 3: 60, 4: 80, 5: 100, 6: 120, 7: 140, 8: 160, 9: 180, 10: 200}
        return rotate_rates[num_active_reactors]

    def get_ps_voltage(self, num_active_reactors):
        """Get the voltage of the power supply."""
        voltages = {0: 0, 1: 10, 2: 20, 3: 30, 4: 40, 5: 50, 6: 60, 7: 70, 8: 80, 9: 90, 10: 100}
        return voltages[num_active_reactors]

