import os
import sys
import time
import logging
import threading
from datetime import datetime
import yaml
from dotenv import load_dotenv

from hue_controller import HueController
from deck_manager import DeckManager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class StreamDeckApp:
    def __init__(self):
        # 1. Load environment configurations
        load_dotenv()
        
        self.bridge_ip = os.getenv("HUE_BRIDGE_IP", "127.0.0.1")
        self.username = os.getenv("HUE_USERNAME", "mock_user")
        self.simulator_mode = os.getenv("SIMULATOR_MODE", "True").lower() in ("true", "1", "yes")

        logging.info("StreamDeckApp: Loading configuration files...")
        
        # 2. Load and parse config.yaml safely
        self.config_path = "/home/zee/code/streamdeck/config.yaml"
        self.buttons_config = {}
        self.load_config()

        # 3. Initialize Controller & Deck Manager
        self.hue = HueController(
            bridge_ip=self.bridge_ip, 
            username=self.username, 
            simulator_mode=self.simulator_mode
        )
        self.deck_mgr = DeckManager(simulator_mode=self.simulator_mode)
        
        # Keep track of active clock widgets
        self.clock_buttons = []
        self.running = True

    def load_config(self):
        """
        Parses config.yaml safely and structures the button configuration map.
        """
        if not os.path.exists(self.config_path):
            logging.error(f"StreamDeckApp: Configuration file not found at {self.config_path}")
            sys.exit(1)

        try:
            with open(self.config_path, "r") as f:
                # Enforce safe parsing to prevent arbitrary code execution vulnerabilities
                config_data = yaml.safe_load(f)
                
            buttons_list = config_data.get("buttons", [])
            for btn in buttons_list:
                index = btn.get("index")
                if index is not None:
                    self.buttons_config[int(index)] = btn
            logging.info(f"StreamDeckApp: Successfully loaded {len(self.buttons_config)} button mappings.")
        except Exception as e:
            logging.error(f"StreamDeckApp: Failed to parse config.yaml: {e}")
            sys.exit(1)

    def update_button_state(self, index: int):
        """
        Queries current state of a device and redraws its button LCD image.
        """
        config = self.buttons_config.get(index)
        if not config:
            return

        device_type = config.get("device_type")
        label = config.get("label", "")
        icon = config.get("icon")

        if device_type in ("light", "plug"):
            target_id = config.get("target")
            state = self.hue.get_light_state(target_id)
            
            # Smart plugs don't have brightness, so we pass None
            brightness = state.get("bri") if device_type == "light" else None
            # Convert 0-254 Hue brightness back to 0-100% for display
            brightness_pct = int((brightness / 254.0) * 100) if brightness is not None else None
            
            self.deck_mgr.update_button(
                index=index,
                label=label,
                device_type=device_type,
                is_on=state.get("on", False),
                brightness=brightness_pct,
                icon_path=icon
            )
        elif device_type == "widget" and config.get("action_type") == "clock":
            # For clocks, the background thread handles periodic redraws, 
            # but we can do an initial placeholder render here.
            now_str = datetime.now().strftime("%H:%M")
            self.deck_mgr.update_button(
                index=index,
                label=label,
                device_type="widget",
                is_on=True,
                icon_path=icon,
                text_override=now_str
            )

    def on_button_press(self, index: int):
        """
        Callback handler called by DeckManager when a D200 button is pressed.
        """
        config = self.buttons_config.get(index)
        if not config:
            logging.warning(f"StreamDeckApp: Pressed unconfigured button index: {index}")
            return

        action_type = config.get("action_type")
        target_id = config.get("target")

        logging.info(f"StreamDeckApp: Button {index} pressed. Action: {action_type}, Target: {target_id}")

        if action_type == "hue_toggle" and target_id:
            success = self.hue.toggle_light(target_id)
            if success:
                # Instantly update display state
                self.update_button_state(index)
        elif action_type == "clock":
            # Interaction: Show date instead of time briefly upon pressing the clock widget
            now_date = datetime.now().strftime("%d/%m")
            logging.info(f"StreamDeckApp: Clock button pressed. Temporarily showing date: {now_date}")
            self.deck_mgr.update_button(
                index=index,
                label="Date",
                device_type="widget",
                is_on=True,
                icon_path=config.get("icon"),
                text_override=now_date
            )
            # Spawn a timer thread to revert back to clock time after 3 seconds
            threading.Timer(3.0, self.update_button_state, args=[index]).start()
        else:
            logging.warning(f"StreamDeckApp: Action type '{action_type}' is not supported or missing target.")

    def run_clock_daemon(self):
        """
        Daemon thread task updating any mapped clock widgets every minute.
        """
        logging.info("StreamDeckApp: Background Clock Widget Daemon started.")
        while self.running:
            try:
                now_str = datetime.now().strftime("%H:%M")
                for index in self.clock_buttons:
                    config = self.buttons_config.get(index)
                    if config:
                        self.deck_mgr.update_button(
                            index=index,
                            label=config.get("label", "Time"),
                            device_type="widget",
                            is_on=True,
                            icon_path=config.get("icon"),
                            text_override=now_str
                        )
                # Calculate sleep duration to align with the next full minute (reduces USB overhead)
                now = datetime.now()
                sleep_seconds = 60 - now.second - (now.microsecond / 1000000.0)
                time.sleep(sleep_seconds)
            except Exception as e:
                logging.error(f"StreamDeckApp: Error in Clock Daemon loop: {e}")
                time.sleep(5)

    def run_interactive_simulator(self):
        """
        Interactive command-line interface thread for Simulator Mode.
        Enables the user to simulate button presses by typing numbers in the terminal.
        """
        logging.info("\n" + "="*60)
        logging.info("  SIMULATOR ACTIVE: Type a button index (0-12) to simulate a press.")
        logging.info("  Type 'q' or 'exit' to shut down gracefully.")
        logging.info("="*60 + "\n")
        
        while self.running:
            try:
                # Read user input safely from stdin
                user_input = sys.stdin.readline().strip()
                if not user_input:
                    continue
                if user_input.lower() in ("q", "exit", "quit"):
                    logging.info("StreamDeckApp: Shutdown requested from simulator console.")
                    self.running = False
                    break
                
                # Check if input is a valid button index
                if user_input.isdigit():
                    btn_idx = int(user_input)
                    if btn_idx in self.buttons_config:
                        self.deck_mgr.simulate_press(btn_idx)
                    else:
                        logging.warning(f"Simulator: Button index {btn_idx} is not mapped in config.yaml")
                else:
                    logging.warning("Simulator: Invalid input. Type an integer between 0 and 12, or 'q' to quit.")
            except Exception as e:
                logging.error(f"Simulator Console Exception: {e}")
                break

    def start(self):
        """
        Initializes and starts the main application loop and daemon threads.
        """
        # Register the button callback with DeckManager
        self.deck_mgr.register_callback(self.on_button_press)

        # Draw initial button states
        for index in self.buttons_config:
            self.update_button_state(index)
            # Identify buttons configured as clock widgets
            config = self.buttons_config.get(index)
            if config and config.get("action_type") == "clock":
                self.clock_buttons.append(index)

        # Start the clock widget background thread if there are any clock buttons
        if self.clock_buttons:
            clock_thread = threading.Thread(target=self.run_clock_daemon, daemon=True)
            clock_thread.start()

        # If in Simulator Mode, spawn the interactive console thread
        if self.simulator_mode:
            console_thread = threading.Thread(target=self.run_interactive_simulator, daemon=True)
            console_thread.start()

        # Keep main thread alive
        try:
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            logging.info("StreamDeckApp: KeyboardInterrupt detected. Shutting down...")
        finally:
            self.running = False
            self.deck_mgr.close()
            logging.info("StreamDeckApp: Application terminated safely.")

if __name__ == "__main__":
    app = StreamDeckApp()
    app.start()
