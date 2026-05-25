import os
import sys
import time
import logging
import threading
import fcntl
from datetime import datetime
import yaml
from dotenv import load_dotenv

from hue_controller import HueController
from deck_manager import DeckManager
from weather_service import WeatherService

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class StreamDeckApp:
    def __init__(self):
        # Single Instance Lock Enforcement
        self.lock_file_path = "/home/zee/code/streamdeck/app.lock"
        try:
            self.lock_file = open(self.lock_file_path, "w")
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_file.write(str(os.getpid()))
            self.lock_file.flush()
        except (IOError, BlockingIOError):
            logging.error("StreamDeckApp: Another instance is already running. Aborting.")
            sys.exit(1)

        # 1. Load environment configurations
        load_dotenv()
        
        self.bridge_ip = os.getenv("HUE_BRIDGE_IP", "127.0.0.1")
        self.username = os.getenv("HUE_USERNAME", "mock_user")
        self.simulator_mode = os.getenv("SIMULATOR_MODE", "True").lower() in ("true", "1", "yes")

        logging.info("StreamDeckApp: Loading configuration files...")
        
        # 2. Load and parse config.yaml safely
        self.config_path = "/home/zee/code/streamdeck/config.yaml"
        self.buttons_config = {}
        self.font_size_label = 12
        self.font_size_status = 10
        self.margin_label = 10
        self.margin_status = 25
        self.small_window_mode = 0
        self.state_sync_interval = 5
        self.screen_sleep_start = "22:00"
        self.screen_sleep_end = "07:00"
        self.screen_sleep_timeout = 300
        self.last_activity_time = time.time()
        self.load_config()

        # 3. Initialize Controller & Deck Manager
        self.hue = HueController(
            bridge_ip=self.bridge_ip, 
            username=self.username, 
            simulator_mode=self.simulator_mode
        )
        self.openweather_api_key = os.getenv("OPENWEATHER_API_KEY", "")
        self.openweather_city = os.getenv("OPENWEATHER_CITY", "Sao Paulo,BR")
        self.weather_service = WeatherService(
            api_key=self.openweather_api_key,
            city=self.openweather_city
        )
        self.deck_mgr = DeckManager(
            simulator_mode=self.simulator_mode,
            font_size_label=self.font_size_label,
            font_size_status=self.font_size_status,
            margin_label=self.margin_label,
            margin_status=self.margin_status,
            small_window_mode=self.small_window_mode
        )
        
        # Register a callback to reset activity timer when screen is woken up
        self.deck_mgr.register_wake_callback(self.reset_activity_timer)

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
                
            self.font_size_label = config_data.get("font_size_label", 12)
            self.font_size_status = config_data.get("font_size_status", 10)
            self.margin_label = config_data.get("margin_label", 10)
            self.margin_status = config_data.get("margin_status", 25)
            self.small_window_mode = config_data.get("small_window_mode", 0)
            self.state_sync_interval = int(config_data.get("state_sync_interval", 5))
            self.screen_sleep_start = config_data.get("screen_sleep_start", "22:00")
            self.screen_sleep_end = config_data.get("screen_sleep_end", "07:00")
            self.screen_sleep_timeout = int(config_data.get("screen_sleep_timeout", 300))
            
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
                icon_path=icon,
                reachable=state.get("reachable", True)
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
        elif device_type == "widget" and config.get("action_type") in ("weather", "weather+1"):
            action = config.get("action_type")
            weather_data = self.weather_service.get_weather_data()
            day_data = weather_data.get(action)
            if day_data:
                min_temp = day_data["min_temp"]
                max_temp = day_data["max_temp"]
                w_type = day_data["type"]
                
                # Format: min°/max° (e.g. 18°/26°)
                temp_str = f"{int(round(min_temp))}°/{int(round(max_temp))}°"
                self.deck_mgr.update_button(
                    index=index,
                    label=label,
                    device_type="widget",
                    is_on=True,
                    icon_path=icon,
                    text_override=temp_str,
                    weather_type=w_type,
                    min_temp=min_temp,
                    max_temp=max_temp
                )

    def on_button_press(self, index: int):
        """
        Callback handler called by DeckManager when a D200 button is pressed.
        """
        self.reset_activity_timer()
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
        elif action_type in ("weather", "weather+1"):
            logging.info(f"StreamDeckApp: Weather button {index} pressed. Force-refreshing weather data...")
            # Temporarily show REFRESHING... feedback
            self.deck_mgr.update_button(
                index=index,
                label=config.get("label", ""),
                device_type="widget",
                is_on=True,
                icon_path=config.get("icon"),
                text_override="REFRESHING..."
            )
            self.weather_service.clear_cache()
            
            # Spawn a background thread to re-fetch and paint both buttons
            def do_refresh():
                self.weather_service.get_weather_data()
                for w_idx, w_config in self.buttons_config.items():
                    if w_config.get("device_type") == "widget" and w_config.get("action_type") in ("weather", "weather+1"):
                        self.update_button_state(w_idx)
                        
            threading.Thread(target=do_refresh, daemon=True).start()
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

    def run_state_sync_daemon(self):
        """
        Daemon thread task periodically polling the Hue Bridge to synchronize
        device states on the Stream Deck buttons if altered externally.
        """
        logging.info("StreamDeckApp: Background State Sync Daemon started.")
        while self.running:
            try:
                # Check and apply screen auto sleep logic
                self.check_screen_sleep()

                # Query all lights in a single network request to minimize bridge latency
                all_devices = self.hue.list_devices()
                for index, config in self.buttons_config.items():
                    device_type = config.get("device_type")
                    if device_type in ("light", "plug") and all_devices:
                        target_id = config.get("target")
                        if target_id and target_id in all_devices:
                            device_data = all_devices[target_id]
                            
                            # Extract state safely supporting both real Hue API and Simulator mock schema
                            if "state" in device_data:
                                state = device_data["state"]
                            else:
                                state = device_data
                                
                            is_on = state.get("on", False)
                            reachable = state.get("reachable", True)
                            brightness = state.get("bri") if device_type == "light" else None
                            brightness_pct = int((brightness / 254.0) * 100) if brightness is not None else None
                            
                            # Push redraw to display
                            self.deck_mgr.update_button(
                                index=index,
                                label=config.get("label", ""),
                                device_type=device_type,
                                is_on=is_on,
                                brightness=brightness_pct,
                                icon_path=config.get("icon"),
                                reachable=reachable
                            )
                    elif device_type == "widget" and config.get("action_type") in ("weather", "weather+1"):
                        self.update_button_state(index)
                # Poll every dynamic sync interval configured by user
                time.sleep(self.state_sync_interval)
            except Exception as e:
                logging.error(f"StreamDeckApp: Error in State Sync Daemon loop: {e}")
                time.sleep(self.state_sync_interval)

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

        # Start the background state synchronization daemon thread
        sync_thread = threading.Thread(target=self.run_state_sync_daemon, daemon=True)
        sync_thread.start()

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

    def reset_activity_timer(self):
        """
        Resets the last user activity timestamp to keep the screen awake.
        """
        self.last_activity_time = time.time()
        logging.info("StreamDeckApp: User activity detected. Resetting sleep timer.")

    def is_within_sleep_window(self) -> bool:
        """
        Helper method to check if the current time is within the sleep schedule.
        Supports time windows that span across midnight (e.g., 22:00 to 07:00).
        """
        if not self.screen_sleep_start or not self.screen_sleep_end:
            return False

        try:
            now = datetime.now().time()
            start = datetime.strptime(self.screen_sleep_start, "%H:%M").time()
            end = datetime.strptime(self.screen_sleep_end, "%H:%M").time()

            if start <= end:
                # Same day window (e.g., 14:00 to 18:00)
                return start <= now <= end
            else:
                # Window spans midnight (e.g., 22:00 to 07:00)
                return now >= start or now <= end
        except Exception as e:
            logging.error(f"StreamDeckApp: Error parsing sleep schedule times: {e}")
            return False

    def check_screen_sleep(self):
        """
        Evaluation routine to automatically check and apply Screen Auto-Sleep.
        """
        # 1. If screen auto-sleep is fully disabled globally, do nothing
        if self.screen_sleep_timeout == 0 and not (self.screen_sleep_start and self.screen_sleep_end):
            return

        now = time.time()
        inactivity_seconds = now - self.last_activity_time
        in_sleep_window = self.is_within_sleep_window()

        # Determine if the screen should be off
        should_sleep = False

        if self.screen_sleep_timeout > 0:
            has_window = bool(self.screen_sleep_start and self.screen_sleep_end)
            if has_window:
                if in_sleep_window and inactivity_seconds >= self.screen_sleep_timeout:
                    should_sleep = True
            else:
                if inactivity_seconds >= self.screen_sleep_timeout:
                    should_sleep = True

        # 2. Apply state transitions
        if should_sleep:
            if self.deck_mgr.screen_on:
                logging.info(f"StreamDeckApp: Auto-sleep triggered (idle for {int(inactivity_seconds)}s). Turning screen OFF.")
                self.deck_mgr.screen_on = False
                self.deck_mgr.set_screen_brightness(0)
        else:
            # If the screen should be ON but is currently OFF:
            if not self.deck_mgr.screen_on:
                has_window = bool(self.screen_sleep_start and self.screen_sleep_end)
                if has_window and not in_sleep_window:
                    logging.info("StreamDeckApp: Outside sleep window. Ensuring screen is ON.")
                    self.deck_mgr.screen_on = True
                    self.deck_mgr.set_screen_brightness(80)

if __name__ == "__main__":
    app = StreamDeckApp()
    app.start()
