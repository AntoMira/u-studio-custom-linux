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
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # Single Instance Lock Enforcement
        self.lock_file_path = os.path.join(base_dir, "app.lock")
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
        self.config_path = os.path.join(base_dir, "config.yaml")
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
        self.pc_monitor_mode = "pull"
        self.pc_monitor_ip = ""
        self.pc_monitor_port = 8085
        self.pc_sync_interval = 60
        self.device_stats = {}      # Map (ip, port) -> telemetry dict
        self.device_last_update = {} # Map (ip, port) -> timestamp
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
            self.pc_monitor_mode = config_data.get("pc_monitor_mode", "pull")
            self.pc_monitor_ip = config_data.get("pc_monitor_ip", "localhost")
            self.pc_monitor_port = int(config_data.get("pc_monitor_port", 8085))
            self.pc_sync_interval = int(config_data.get("pc_sync_interval", 60))
            
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
        elif device_type == "widget" and config.get("action_type") in ("weather_forecast", "weather_forecast+1"):
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
        elif device_type == "widget" and config.get("action_type") == "weather":
            # Current Weather Widget
            weather_data = self.weather_service.get_weather_data()
            current_data = weather_data.get("weather")
            if current_data:
                temp = current_data["temp"]
                pop = current_data["pop"]
                w_type = current_data["type"]
                
                # Format: "Temp° | POP%" (e.g. 21° | 40%)
                pop_pct = int(round(pop * 100))
                temp_str = f"{int(round(temp))}° | {pop_pct}%"
                self.deck_mgr.update_button(
                    index=index,
                    label=label,
                    device_type="widget",
                    is_on=True,
                    icon_path=icon,
                    text_override=temp_str,
                    weather_type=w_type,
                    min_temp=temp,
                    max_temp=None
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
        elif action_type in ("weather", "weather_forecast", "weather_forecast+1"):
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
            
            # Spawn a background thread to re-fetch and paint weather buttons
            def do_refresh():
                self.weather_service.get_weather_data()
                for w_idx, w_config in self.buttons_config.items():
                    if w_config.get("device_type") == "widget" and w_config.get("action_type") in ("weather", "weather_forecast", "weather_forecast+1"):
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
                    elif device_type == "widget" and config.get("action_type") in ("weather", "weather_forecast", "weather_forecast+1"):
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
                elif action_type in ("pc_monitor", "gpu_monitor"):
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

    def find_any_temperature_sensor(self, node):
        """
        Fallback recursive search for any temperature sensor with '°C' in its Value field.
        Prioritizes nodes containing 'cpu', 'package', or 'core' in their text label.
        """
        if not node:
            return None

        # Check children for Temperature type or °C
        children = node.get("Children", [])
        for child in children:
            t_type = child.get("Type", "")
            val_str = str(child.get("Value", ""))
            text_str = child.get("Text", "").lower()

            if t_type == "Temperature" or "°c" in val_str.lower():
                parsed = self.parse_lhm_value(val_str)
                if parsed is not None and 15.0 <= parsed <= 115.0:
                    return parsed

        for child in children:
            found = self.find_any_temperature_sensor(child)
            if found is not None:
                return found
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
        Daemon thread task fetching data.json from LibreHardwareMonitor web servers
        for all registered pc_monitor buttons.
        """
        logging.info("StreamDeckApp: Background PC Monitor HTTP Pull Daemon started.")
        while self.running:
            # Gather all unique target endpoints (ip, port) configured across buttons
            targets = set()
            for index in self.pc_monitor_buttons:
                config = self.buttons_config.get(index, {})
                btn_mode = config.get("mode", self.pc_monitor_mode)
                if btn_mode == "pull":
                    btn_ip = config.get("ip", self.pc_monitor_ip).strip()
                    btn_port = int(config.get("port", self.pc_monitor_port))
                    if btn_ip and btn_ip.lower() not in ("localhost", "127.0.0.1", "::1"):
                        targets.add((btn_ip, btn_port))

            for ip, port in targets:
                url = f"http://{ip}:{port}/data.json"
                try:
                    response = requests.get(url, timeout=2.0)
                    if response.status_code == 200:
                        tree = response.json()
                        pc_name = tree.get("Text", "PC")
                        if pc_name == "SensorTree" and tree.get("Children"):
                            pc_name = tree["Children"][0].get("Text", "PC")

                        cpu_temp_paths = [
                            ["cpu", "temperatures", "core (tctl/tdie)"],
                            ["amd", "temperatures", "core (tctl/tdie)"],
                            ["ryzen", "temperatures", "core (tctl/tdie)"],
                            ["cpu", "temperatures", "ccd1 (tdie)"],
                            ["amd", "temperatures", "ccd1 (tdie)"],
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
                            ["cpu", "temperatures", "core temperature"],
                            ["cpu", "temperatures"],
                            ["temperatures", "cpu"],
                            ["temperatures", "package"],
                            ["temperatures", "core"],
                            ["temperatures"]
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
                            ["load", "cpu total"],
                            ["load", "total"],
                        ]
                        ram_usage_paths = [
                            ["generic memory", "load", "memory"],
                            ["memory", "load", "memory"],
                            ["memory", "load", "memory load"],
                            ["load", "memory"],
                        ]

                        gpu_temp_paths = [
                            ["nvidia", "temperatures", "gpu core"],
                            ["geforce", "temperatures", "gpu core"],
                            ["radeon", "temperatures", "gpu core"],
                            ["gpu", "temperatures", "gpu core"],
                            ["nvidia", "temperatures", "gpu temperature"],
                            ["radeon", "temperatures", "gpu temperature"],
                            ["gpu", "temperatures", "gpu temperature"],
                            ["gpu core"],
                        ]
                        gpu_usage_paths = [
                            ["nvidia", "load", "gpu core"],
                            ["geforce", "load", "gpu core"],
                            ["radeon", "load", "gpu core"],
                            ["gpu", "load", "gpu core"],
                            ["nvidia", "load", "gpu"],
                            ["gpu", "load", "gpu"],
                        ]
                        gpu_vram_paths = [
                            ["nvidia", "load", "gpu memory"],
                            ["geforce", "load", "gpu memory"],
                            ["radeon", "load", "gpu memory"],
                            ["gpu", "load", "gpu memory"],
                            ["nvidia", "load", "gpu memory used"],
                            ["gpu", "load", "gpu memory used"],
                        ]

                        cpu_temp = self.parse_lhm_value(self.get_sensor_value(tree, cpu_temp_paths))
                        if cpu_temp is None:
                            cpu_temp = self.find_any_temperature_sensor(tree)

                        cpu_usage = self.parse_lhm_value(self.get_sensor_value(tree, cpu_usage_paths)) or 0.0
                        ram_usage = self.parse_lhm_value(self.get_sensor_value(tree, ram_usage_paths)) or 0.0

                        gpu_temp = self.parse_lhm_value(self.get_sensor_value(tree, gpu_temp_paths))
                        gpu_usage = self.parse_lhm_value(self.get_sensor_value(tree, gpu_usage_paths)) or 0.0
                        gpu_vram = self.parse_lhm_value(self.get_sensor_value(tree, gpu_vram_paths)) or 0.0

                        self.device_stats[(ip, port)] = {
                            "pc_name": pc_name,
                            "cpu_usage": round(cpu_usage, 1),
                            "cpu_temp": round(cpu_temp, 1) if cpu_temp is not None else None,
                            "ram_usage": round(ram_usage, 1),
                            "gpu_usage": round(gpu_usage, 1),
                            "gpu_vram": round(gpu_vram, 1),
                            "gpu_temp": round(gpu_temp, 1) if gpu_temp is not None else None,
                            "tree": tree
                        }
                        self.device_last_update[(ip, port)] = time.time()
                except Exception as e:
                    logging.debug(f"StreamDeckApp: Failed to fetch LHM metrics for {ip}:{port}: {e}")

            time.sleep(5)

    def get_local_server_stats(self):
        """
        Collects system metrics from the host server (CPU usage, Memory usage, CPU Temp).
        Supports Linux, Windows, and macOS via native system files or fallbacks.
        """
        cpu_usage = None
        mem_usage = None
        temp_val = None

        # 1. CPU Usage (%)
        try:
            # Read /proc/stat if Linux
            if os.path.exists("/proc/stat"):
                with open("/proc/stat", "r") as f:
                    fields = f.readline().split()[1:]
                    vals = [float(x) for x in fields]
                    idle = vals[3] + vals[4]
                    total = sum(vals)
                    if hasattr(self, "_prev_cpu"):
                        prev_idle, prev_total = self._prev_cpu
                        idle_delta = idle - prev_idle
                        total_delta = total - prev_total
                        if total_delta > 0:
                            cpu_usage = 100.0 * (1.0 - idle_delta / total_delta)
                    self._prev_cpu = (idle, total)
        except Exception:
            pass

        # Fallback for CPU usage
        if cpu_usage is None:
            try:
                load1, _, _ = os.getloadavg()
                cpu_count = os.cpu_count() or 1
                cpu_usage = min(100.0, (load1 / cpu_count) * 100.0)
            except Exception:
                cpu_usage = 0.0

        # 2. Physical Memory Usage (%)
        try:
            if os.path.exists("/proc/meminfo"):
                mem_data = {}
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        parts = line.split(":")
                        if len(parts) == 2:
                            k = parts[0].strip()
                            v = parts[1].strip().split()[0]
                            mem_data[k] = float(v)
                total_mem = mem_data.get("MemTotal", 1.0)
                free_mem = mem_data.get("MemFree", 0.0)
                buffers = mem_data.get("Buffers", 0.0)
                cached = mem_data.get("Cached", 0.0)
                sreclaimable = mem_data.get("SReclaimable", 0.0)
                
                # Physical RAM used directly by applications (excluding filesystem cache/buffers)
                used_physical = total_mem - free_mem - buffers - cached - sreclaimable
                mem_usage = 100.0 * (used_physical / total_mem)
        except Exception:
            pass

        if mem_usage is None:
            mem_usage = 0.0

        # 3. CPU Temperature (°C)
        try:
            # Scan thermal zone files on Linux
            thermal_dirs = ["/sys/class/thermal/thermal_zone0/temp", "/sys/class/hwmon/hwmon0/temp1_input", "/sys/class/hwmon/hwmon1/temp1_input"]
            for t_path in thermal_dirs:
                if os.path.exists(t_path):
                    with open(t_path, "r") as f:
                        val = float(f.read().strip())
                        if val > 1000:
                            val /= 1000.0
                        if 0 <= val <= 120:
                            temp_val = val
                            break
        except Exception:
            pass

        if temp_val is None:
            temp_val = 45.0 # Fallback baseline temp if no sensor file accessible

        return {
            "pc_name": "LOCALHOST",
            "cpu_usage": round(cpu_usage, 1),
            "ram_usage": round(mem_usage, 1),
            "cpu_temp": round(temp_val, 1)
        }

    def run_pc_monitor_daemon(self):
        """
        Daemon thread task updating pc_monitor widgets periodically based on per-button configs.
        Renders 3 progress bars: CPU %, MEM %, and TEMP °C.
        """
        logging.info("StreamDeckApp: Background PC Monitor Daemon (3-bar mode) started.")
        last_button_update = {} # button_index -> timestamp
        
        while self.running:
            try:
                now = time.time()
                for index in self.pc_monitor_buttons:
                    config = self.buttons_config.get(index)
                    if not config:
                        continue

                    btn_ip = config.get("ip", self.pc_monitor_ip).strip()
                    btn_port = int(config.get("port", self.pc_monitor_port))
                    btn_interval = int(config.get("sync_interval", self.pc_sync_interval))
                    label = config.get("label", "Monitor")

                    # Check if it's time to update this specific button
                    last_upd = last_button_update.get(index, 0)
                    if (now - last_upd) < btn_interval:
                        continue

                    last_button_update[index] = now

                    if btn_ip.lower() in ("localhost", "127.0.0.1", "::1"):
                        # Host server local monitoring
                        stats = self.get_local_server_stats()
                        self.deck_mgr.update_button(
                            index=index,
                            label=label,
                            device_type="widget",
                            is_on=True,
                            reachable=True,
                            text_override="",
                            cpu_pct=stats["cpu_usage"],
                            mem_pct=stats["ram_usage"],
                            temp_val=stats["cpu_temp"]
                        )
                    else:
                        # Remote PC monitoring by (ip, port)
                        dev_stats = self.device_stats.get((btn_ip, btn_port))
                        dev_last = self.device_last_update.get((btn_ip, btn_port), 0)
                        is_online = (now - dev_last) <= (btn_interval * 3) and bool(dev_stats)

                        if not is_online:
                            self.deck_mgr.update_button(
                                index=index,
                                label=label,
                                device_type="widget",
                                is_on=False,
                                reachable=False,
                                text_override="OFFLINE",
                                icon_path="pc_monitor"
                            )
                        else:
                            action_type = config.get("action_type")
                            monitor_type = config.get("monitor_type")

                            is_gpu_widget = (action_type == "gpu_monitor" or monitor_type == "gpu")

                            if is_gpu_widget:
                                cpu_pct = dev_stats.get("gpu_usage", 0.0)
                                mem_pct = dev_stats.get("gpu_vram", 0.0)
                                temp_val = dev_stats.get("gpu_temp")
                                col_labels = ("GPU", "RAM", "TMP")
                            else:
                                cpu_pct = dev_stats.get("cpu_usage", 0.0)
                                mem_pct = dev_stats.get("ram_usage", 0.0)
                                temp_val = dev_stats.get("cpu_temp")
                                col_labels = ("CPU", "MEM", "TMP")

                            # Check if button specifies a custom temp_sensor keyword override
                            custom_temp = config.get("temp_sensor")
                            if custom_temp and "tree" in dev_stats:
                                custom_val = self.parse_lhm_value(
                                    self.find_sensor_by_path(dev_stats["tree"], [custom_temp]) or
                                    self.find_sensor_by_path(dev_stats["tree"], ["temperatures", custom_temp])
                                )
                                if custom_val is not None:
                                    temp_val = custom_val

                            self.deck_mgr.update_button(
                                index=index,
                                label=label,
                                device_type="widget",
                                is_on=True,
                                reachable=True,
                                text_override="",
                                cpu_pct=cpu_pct,
                                mem_pct=mem_pct,
                                temp_val=temp_val,
                                col_labels=col_labels
                            )

                time.sleep(1)
            except Exception as e:
                logging.error(f"StreamDeckApp: Error in PC Monitor Daemon: {e}")
                time.sleep(2)

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
