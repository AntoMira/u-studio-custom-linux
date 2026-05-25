import os
import sys
import time
import logging
import threading
import fcntl
import requests
from datetime import datetime
import yaml
from dotenv import load_dotenv

try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        ZoneInfo = None

from hue_controller import HueController
from deck_manager import DeckManager
from weather_service import WeatherService

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class StreamDeckApp:
    def __init__(self):
        # Single Instance Lock Enforcement
        self.lock_file_path = "/home/zee/code/streamdeck/server/app.lock"
        disable_lock = os.getenv("DISABLE_LOCK", "False").lower() in ("true", "1", "yes")
        if not disable_lock:
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

        # Parse TIMEZONE configuration safely with elegant fallbacks
        self.timezone_str = os.getenv("TIMEZONE", "").strip()
        self.timezone = None
        if self.timezone_str:
            if ZoneInfo is not None:
                try:
                    self.timezone = ZoneInfo(self.timezone_str)
                    logging.info(f"StreamDeckApp: Configured timezone: {self.timezone_str}")
                except Exception as e:
                    logging.error(f"StreamDeckApp: Failed to load timezone '{self.timezone_str}': {e}. Falling back to system timezone.")
            else:
                logging.warning("StreamDeckApp: zoneinfo module is unavailable. Falling back to system timezone.")

        logging.info("StreamDeckApp: Loading configuration files...")
        
        # 2. Load and parse config.yaml safely
        self.config_path = "/home/zee/code/streamdeck/server/config.yaml"
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
        self.pc_monitor_mode = "push"
        self.pc_monitor_ip = ""
        self.pc_monitor_port = 9999
        self.pc_stats = {}
        self.pc_stats_last_update = 0
        self.pc_monitor_buttons = []
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
            self.pc_monitor_mode = config_data.get("pc_monitor_mode", "push")
            self.pc_monitor_ip = config_data.get("pc_monitor_ip", "")
            self.pc_monitor_port = int(config_data.get("pc_monitor_port", 9999 if self.pc_monitor_mode == "push" else 8085))
            
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
            now_str = datetime.now(self.timezone).strftime("%H:%M")
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
        elif device_type == "widget" and config.get("action_type") == "pc_monitor":
            self.deck_mgr.update_button(
                index=index,
                label=label,
                device_type="widget",
                is_on=False,
                reachable=False,
                icon_path="pc_monitor",
                text_override="WAITING..."
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
            now_date = datetime.now(self.timezone).strftime("%d/%m")
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
                now_str = datetime.now(self.timezone).strftime("%H:%M")
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
                now = datetime.now(self.timezone)
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
            # Identify widgets
            config = self.buttons_config.get(index)
            if config:
                action_type = config.get("action_type")
                if action_type == "clock":
                    self.clock_buttons.append(index)
                elif action_type == "pc_monitor":
                    self.pc_monitor_buttons.append(index)

        # Start the clock widget background thread if there are any clock buttons
        if self.clock_buttons:
            clock_thread = threading.Thread(target=self.run_clock_daemon, daemon=True)
            clock_thread.start()

        # Start the PC Monitor background telemetries and carousel thread if pc_monitor buttons exist
        if self.pc_monitor_buttons:
            if self.pc_monitor_mode == "pull":
                pull_thread = threading.Thread(target=self.run_pc_monitor_pull_daemon, daemon=True)
                pull_thread.start()
            else:
                if hasattr(self, "run_udp_listener"):
                    udp_thread = threading.Thread(target=self.run_udp_listener, daemon=True)
                    udp_thread.start()
            pc_monitor_thread = threading.Thread(target=self.run_pc_monitor_daemon, daemon=True)
            pc_monitor_thread.start()

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

    def find_sensor_by_path(self, node, path_keywords, depth=0):
        """
        Recursively searches the sensor node based on hierarchical keywords.
        e.g., path_keywords=["intel core", "temperatures", "cpu package"]
        """
        if not node:
            return None
        text = node.get("Text", "").lower()
        keyword = path_keywords[depth].lower()
        
        if keyword in text:
            if depth == len(path_keywords) - 1:
                return node.get("Value")
            
            for child in node.get("Children", []):
                val = self.find_sensor_by_path(child, path_keywords, depth + 1)
                if val is not None:
                    return val
                    
        for child in node.get("Children", []):
            val = self.find_sensor_by_path(child, path_keywords, depth)
            if val is not None:
                return val
        return None

    def get_sensor_value(self, tree, paths):
        for path in paths:
            val = self.find_sensor_by_path(tree, path)
            if val is not None:
                return val
        return None

    def parse_lhm_value(self, val_str):
        if val_str is None:
            return None
        try:
            # Strip standard units and spaces
            cleaned = val_str.replace("°C", "").replace("%", "").replace("GB", "").strip()
            cleaned = cleaned.replace(",", ".")
            return float(cleaned)
        except Exception as e:
            logging.debug(f"StreamDeckApp: Failed to parse sensor value '{val_str}': {e}")
            return None

    def run_pc_monitor_pull_daemon(self):
        """
        Daemon thread task fetching data.json from LibreHardwareMonitor web server.
        """
        logging.info("StreamDeckApp: Background PC Monitor HTTP Pull Daemon started.")
        while self.running:
            if not self.pc_monitor_ip:
                logging.warning("StreamDeckApp: PC Monitor mode is 'pull' but pc_monitor_ip is empty.")
                time.sleep(5)
                continue
                
            url = f"http://{self.pc_monitor_ip}:{self.pc_monitor_port}/data.json"
            try:
                # 2-second timeout as specified in the plan
                response = requests.get(url, timeout=2.0)
                if response.status_code == 200:
                    tree = response.json()
                    
                    # 1. Parse PC Name from root or first child
                    pc_name = tree.get("Text", "PC")
                    if pc_name == "SensorTree" and tree.get("Children"):
                        pc_name = tree["Children"][0].get("Text", "PC")
                    
                    # 2. Extract metrics using robust lists of candidate paths
                    cpu_temp_paths = [
                        ["intel", "temperatures", "cpu package"],
                        ["amd", "temperatures", "cpu package"],
                        ["core", "temperatures", "cpu package"],
                        ["ryzen", "temperatures", "cpu package"],
                        ["cpu", "temperatures", "cpu package"],
                        ["intel", "temperatures", "core max"],
                        ["amd", "temperatures", "core max"],
                        ["core", "temperatures", "core max"],
                        ["cpu", "temperatures", "core max"],
                        ["intel", "temperatures", "cpu total"],
                        ["amd", "temperatures", "cpu total"],
                        ["cpu", "temperatures", "cpu total"],
                        ["cpu", "temperatures", "core (tctl/tdie)"],
                        ["cpu", "temperatures", "core temperature"],
                    ]
                    cpu_usage_paths = [
                        ["intel", "load", "cpu total"],
                        ["amd", "load", "cpu total"],
                        ["core", "load", "cpu total"],
                        ["ryzen", "load", "cpu total"],
                        ["cpu", "load", "cpu total"],
                        ["intel", "load", "total"],
                        ["amd", "load", "total"],
                        ["cpu", "load", "total"],
                        ["cpu", "load", "cpu"],
                    ]
                    gpu_temp_paths = [
                        ["nvidia", "temperatures", "gpu core"],
                        ["geforce", "temperatures", "gpu core"],
                        ["radeon", "temperatures", "gpu core"],
                        ["gpu", "temperatures", "gpu core"],
                        ["nvidia", "temperatures", "gpu temperature"],
                        ["radeon", "temperatures", "gpu temperature"],
                        ["gpu", "temperatures", "gpu temperature"],
                    ]
                    gpu_usage_paths = [
                        ["nvidia", "load", "gpu core"],
                        ["geforce", "load", "gpu core"],
                        ["radeon", "load", "gpu core"],
                        ["gpu", "load", "gpu core"],
                        ["nvidia", "load", "gpu memory"],
                        ["gpu", "load", "gpu memory"],
                        ["gpu", "load", "gpu"],
                    ]
                    ram_usage_paths = [
                        ["generic memory", "load", "memory"],
                        ["memory", "load", "memory"],
                        ["memory", "load", "memory load"],
                    ]
                    disk_usage_paths = [
                        ["hdd", "load", "used space"],
                        ["ssd", "load", "used space"],
                        ["drive", "load", "used space"],
                        ["storage", "load", "used space"],
                        ["disk", "load", "used space"],
                    ]
                    
                    cpu_temp = self.parse_lhm_value(self.get_sensor_value(tree, cpu_temp_paths))
                    cpu_usage = self.parse_lhm_value(self.get_sensor_value(tree, cpu_usage_paths)) or 0.0
                    gpu_temp = self.parse_lhm_value(self.get_sensor_value(tree, gpu_temp_paths))
                    gpu_usage = self.parse_lhm_value(self.get_sensor_value(tree, gpu_usage_paths)) or 0.0
                    ram_usage = self.parse_lhm_value(self.get_sensor_value(tree, ram_usage_paths)) or 0.0
                    disk_usage = self.parse_lhm_value(self.get_sensor_value(tree, disk_usage_paths)) or 0.0
                    
                    self.pc_stats = {
                        "pc_name": pc_name,
                        "cpu_usage": cpu_usage,
                        "cpu_temp": cpu_temp,
                        "gpu_usage": gpu_usage,
                        "gpu_temp": gpu_temp,
                        "ram_usage": ram_usage,
                        "disk_usage": disk_usage,
                    }
                    self.pc_stats_last_update = time.time()
                else:
                    logging.warning(f"StreamDeckApp: LHM server returned status code {response.status_code}")
            except Exception as e:
                # Capture connection timeouts and errors gracefully to trigger offline display
                logging.debug(f"StreamDeckApp: Failed to fetch LHM metrics: {e}")
                
            time.sleep(5)

    def run_pc_monitor_daemon(self):
        """
        Daemon thread task updating any mapped pc_monitor widgets every 5 seconds,
        rotating between CPU, GPU, RAM, and Disk metrics.
        """
        logging.info("StreamDeckApp: Background PC Monitor Carousel Daemon started.")
        carousel_index = 0
        while self.running:
            try:
                now = time.time()
                is_online = (now - self.pc_stats_last_update) <= 15.0 and bool(self.pc_stats)

                for index in self.pc_monitor_buttons:
                    config = self.buttons_config.get(index)
                    if not config:
                        continue
                    
                    if not is_online:
                        pc_name = self.pc_stats.get("pc_name", config.get("label", "PC Monitor")) if self.pc_stats else config.get("label", "PC Monitor")
                        self.deck_mgr.update_button(
                            index=index,
                            label=pc_name,
                            device_type="widget",
                            is_on=False,
                            reachable=False,
                            text_override="OFFLINE",
                            icon_path="pc_monitor"
                        )
                    else:
                        pc_name = self.pc_stats.get("pc_name", "DESKTOP")
                        if carousel_index == 0:
                            usage = self.pc_stats.get("cpu_usage", 0.0)
                            temp = self.pc_stats.get("cpu_temp")
                            temp_str = f" ({int(temp)}°)" if temp is not None else ""
                            status_text = f"CPU: {int(usage)}%{temp_str}"
                            self.deck_mgr.update_button(
                                index=index,
                                label=pc_name,
                                device_type="widget",
                                is_on=True,
                                icon_path="cpu",
                                text_override=status_text
                            )
                        elif carousel_index == 1:
                            usage = self.pc_stats.get("gpu_usage", 0.0)
                            temp = self.pc_stats.get("gpu_temp")
                            temp_str = f" ({int(temp)}°)" if temp is not None else ""
                            status_text = f"GPU: {int(usage)}%{temp_str}"
                            self.deck_mgr.update_button(
                                index=index,
                                label=pc_name,
                                device_type="widget",
                                is_on=True,
                                icon_path="gpu",
                                text_override=status_text
                            )
                        elif carousel_index == 2:
                            usage = self.pc_stats.get("ram_usage", 0.0)
                            status_text = f"RAM: {int(usage)}%"
                            self.deck_mgr.update_button(
                                index=index,
                                label=pc_name,
                                device_type="widget",
                                is_on=True,
                                icon_path="ram",
                                text_override=status_text
                            )
                        elif carousel_index == 3:
                            usage = self.pc_stats.get("disk_usage", 0.0)
                            status_text = f"Disk: {int(usage)}%"
                            self.deck_mgr.update_button(
                                index=index,
                                label=pc_name,
                                device_type="widget",
                                is_on=True,
                                icon_path="disk",
                                text_override=status_text
                            )

                carousel_index = (carousel_index + 1) % 4
                time.sleep(5)
            except Exception as e:
                logging.error(f"StreamDeckApp: Error in PC Monitor Daemon: {e}")
                time.sleep(5)

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
            now = datetime.now(self.timezone).time()
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
