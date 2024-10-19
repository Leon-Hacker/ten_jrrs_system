from pump_control import PumpControl
import time

def test_read_pump_parameters():
    # Initialize the PumpControl object
    pump = PumpControl(port='COM13', baudrate=9600, address=1)

    try:
        # Open the serial connection to the pump
        pump.open_connection()

        # Read the pump parameters (flow, pressure, and stroke)
        flow, pressure, stroke = pump.read_pump_parameters()

        # Check if the values were successfully read
        if flow is not None and pressure is not None and stroke is not None:
            print(f"Flow: {flow:.2f} units")
            print(f"Pressure: {pressure:.8f} units")
            print(f"Stroke: {stroke:.2f} units")
        else:
            print("Failed to read pump parameters.")
        
        time.sleep(1)
        status = pump.read_pump_status()
        print(status)


    except Exception as e:
        print(f"Error during pump parameter reading: {e}")

    finally:
        # Close the serial connection
        pump.close_connection()

if __name__ == '__main__':
    test_read_pump_parameters()
