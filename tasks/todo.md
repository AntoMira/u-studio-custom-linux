# Stream Deck Todo List

- [x] **1. Environment Setup**
    - [x] Create Python virtual environment (`venv`)
    - [x] Write `requirements.txt` with dependencies (`requests`, `pyyaml`, `strmdck`, `pillow`, `python-dotenv`)
- [x] **2. Config & Secret Templates**
    - [x] Create `.env.example` defining environment variable keys
    - [x] Create `config.yaml` for custom button-to-Hue action mappings (bulbs and plugs)
    - [x] Create `.gitignore` to protect local credentials
- [x] **3. Philips Hue Controller**
    - [x] Create `hue_controller.py` with local REST Bridge client class
    - [x] Implement `toggle_light()`, `set_brightness()`, and `get_light_state()` with error boundaries
- [x] **4. Deck Manager & Simulator**
    - [x] Create `deck_manager.py` interfacing with PyPI `strmdck`
    - [x] Implement dynamic icon renderer using `Pillow` (text overlay, status color highlights, and "HH:MM" digital clock rendering)
    - [x] Implement robust `SimulatorMode` that saves rendering outputs to `output_sim/` for visual verification
- [x] **5. Main Daemon Orchestrator**
    - [x] Create `main.py` orchestrating connection loops
    - [x] Implement background daemon thread for real-time clock widget updates
    - [x] Implement safe input parsing (`yaml.safe_load`) and button callbacks
- [x] **6. Verification Suite**
    - [x] Create `verify.py` with unit tests for config formatting, Pillow dimensions, and mock APIs
    - [x] Manually verify image renderings and toggling behavior in `output_sim/`
- [x] **7. Documentation**
    - [x] Create `README.md` with setup steps, Hue API token extraction guide, and Linux udev USB rules
- [x] **8. Version Control & GitHub**
    - [x] Initialize Git repository (`git init`)
    - [x] Commit initial project files (`git commit`)
    - [x] Create remote repository on GitHub using `gh` CLI (`gh repo create`)
    - [x] Push to main branch (`git push`) and verify pull/fetch (`git pull`)
- [x] **9. Virtual Environment Runner Script (`run.sh`)**
    - [x] Create `run.sh` with automatic venv setup, requirements installation, and application launching
    - [x] Make `run.sh` executable (`chmod +x run.sh`)
    - [x] Verify script functionality by running the application in simulator mode
- [x] **10. Single Instance Lock Enforcement**
    - [x] Implement robust file lock checking using `fcntl` in `main.py` to prevent duplicate instances
    - [x] Verify enforcement by attempting to run a second instance concurrently
- [x] **11. Python 3.9 Environment & Hard Dependency Integration**
    - [x] Install `python3.9` and `python3.9-venv` on the host system via apt
    - [x] Update `requirements.txt` to uncomment/pin `strmdck==0.1.0rc1`
    - [x] Update `run.sh` to use `python3.9` for virtual environment creation
    - [x] Remove import try/except fallback from `deck_manager.py`, making `strmdck` a hard dependency
    - [x] Recreate virtual environment and verify connection attempts in physical mode
- [x] **12. Small Screen Clock Synchronization**
    - [x] Implement a periodic keep_alive loop in `deck_manager.py` that runs every second
    - [x] Trigger `self.deck.keep_alive()` in physical mode to automatically sync local clock with the D200 small window
    - [x] Add `TIMEZONE` variable in `.env` and `.env.example` to allow user configuration of the small window clock
- [x] **13. Global Font Size Customization**
    - [x] Add `font_size_label` and `font_size_status` to `config.yaml` as global settings
    - [x] Update `main.py` to parse global font settings and pass them to the deck manager
    - [x] Update `deck_manager.py`'s `update_button` to accept and use the custom font sizes with Pillow
    - [x] Verify the custom font sizes render successfully
- [x] **14. Initial Button State Clearing**
    - [x] Pre-populate `self.active_buttons` in `DeckManager` with `None` for all 13 keys on startup
    - [x] Verify that physical buttons are cleanly reset and cleared of old screens on startup
- [x] **15. Global Label Margins Customization**
    - [x] Add `margin_label` and `margin_status` to `config.yaml` as global settings
    - [x] Update `main.py` to parse global label margins and pass them to the deck manager
    - [x] Update `deck_manager.py`'s `update_button` to accept and use the custom margins
    - [x] Verify the custom label margins render successfully
- [x] **16. Small Screen Clock Sync & Button Blackout Fix**
    - [x] Expose `small_window_mode` in `config.yaml` to dynamically customize layout (e.g. Stats mode)
    - [x] Clear default analog overlapping Ulanzi watchface by loading STATS mode on hardware startup
    - [x] Implement a startup sequence reset (setting mode 2, sleeping, then reverting to configured mode) to force the small screen buffer to clear the logo
    - [x] Prevent active buttons from turning off by enforcing full page updates (`update_only=False`) for physical deck uploads
    - [x] Verify that all button displays remain properly illuminated and active after subsequent clock daemon refreshes
- [x] **17. Config Documentation & Clock Widget Styling**
    - [x] Add comments to `config.yaml` with options available for all attributes
    - [x] Modify `deck_manager.py` to remove the blue border (outline) from the clock widget
    - [x] Run verification tests to validate `config.yaml` and rendering logic
    - [x] Manually verify rendered `output_sim/button_12.png` clock image to ensure blue border is removed
- [x] **18. Philips Hue Device Listing Tool**
    - [x] Add list_devices method to HueController class
    - [x] Create list_hue.py script with argparse parameters
    - [x] Create list_hue.sh shell script
    - [x] Make scripts executable and verify device listing in simulator and physical modes

- [x] **19. Periodic Background State Synchronization**
    - [x] Implement run_state_sync_daemon method in main.py
    - [x] Spawn state sync daemon thread on application startup
    - [x] Verify that external device changes are automatically updated on the Stream Deck button screens

- [x] **20. Configurable Polling Interval**
    - [x] Add state_sync_interval setting in config.yaml global settings
    - [x] Update main.py load_config and daemon thread to respect configured state_sync_interval
    - [x] Update verify.py config checks to validate state_sync_interval
    - [x] Run verify.py to validate configuration structure and values

- [x] **21. Firmware Image Cache Invalidation**
    - [x] Add cleanup of older button index cache files in deck_manager.py
    - [x] Implement timestamp-salted icon names for physical updates in deck_manager.py
    - [x] Run verify.py to validate PIL image logic remains unbroken
    - [x] Verify physical Stream Deck displays update in real time

- [x] **22. Status Color Refinement (Green/Red/Gray)**
    - [x] Update update_button signature and color palette logic in deck_manager.py
    - [x] Update update_button_state and state_sync_daemon in main.py to fetch and pass reachable state
    - [x] Adjust verify.py tests to support new update_button signature
    - [x] Run verify.py and manually verify physical D200 buttons color output

- [x] **23. Linux Systemd Service Integration**
    - [x] Create streamdeck.service systemd file template
    - [x] Create start_service.sh systemd service installer script
    - [x] Create stop_service.sh systemd service stopper script
    - [x] Make service scripts executable and verify service control flow

- [x] **24. Visual Style Refactoring (White Text/Icons, Solid Background State Colors)**
    - [x] Create detailed implementation plan and obtain approval
    - [x] Update `update_button` inside `deck_manager.py` with solid bg colors and white text/icons
    - [x] Refactor icon image white-tinting channel logic in `deck_manager.py`
    - [x] Run verification test suite `verify.py` and resolve any breaks
    - [x] Run the application in simulator mode to generate new visual assets
    - [x] Inspect regenerated PNG images in `output_sim/` to verify style correctness

- [x] **25. Screen Auto Sleep & Wake Implementation**
    - [x] Create detailed implementation plan and obtain approval
    - [x] Add configuration settings inside `config.yaml`
    - [x] Add brightness set and keypress intercept wake logic inside `deck_manager.py`
    - [x] Integrate inactivity and sleep time schedules inside `main.py`
    - [x] Verify functionality via unit tests and simulator mode

- [x] **26. Weather Widgets ("weather" & "weather+1")**
    - [x] Create detailed implementation plan and obtain approval
    - [x] Add `OPENWEATHER_API_KEY` and `OPENWEATHER_CITY` to `.env.example`
    - [x] Add example button config for `weather` and `weather+1` in `config.yaml`
    - [x] Create `weather_service.py` with caching and priority-based grouping
    - [x] Update `deck_manager.py` with custom high-contrast geometric weather drawings
    - [x] Update `main.py` to instantiate service, process actions, and support interactive tap refresh
    - [x] Verify functionality via automated tests and simulator mode button image inspection

- [x] **27. PC Performance Monitoring Widget (Windows Network Stats Integration)**
    - [x] Create detailed implementation plan and obtain approval
    - [x] Create mock Windows client script `mock_pc_client.py` for network telemetry simulation
    - [x] Bind UDP Broadcast Listener socket in `main.py` inside a background daemon thread
    - [x] Implement rotation carousel logic in `main.py` (switching metric display every 5 seconds)
    - [x] Update `deck_manager.py` to support premium geometric shapes for pc, cpu, gpu, ram, and disk widgets
    - [x] Implement offline state detection (15-second socket timeout fallback)
    - [x] Add config templates for `pc_monitor_port` and button index layout in `config.yaml`
    - [x] Verify functionality via automated verification tests and simulator mode button image inspection

- [x] **28. Repository Reorganization (Server & Clients Specialization)**
    - [x] Create detailed implementation plan and obtain approval
    - [x] Stop systemd daemon using `./stop_service.sh`
    - [x] Create `server/` and `clients/windows/` directories
    - [x] Move server files (Python scripts, YAML configuration, requirements) into `server/`
    - [x] Move network performance stats client `mock_pc_client.py` into `clients/windows/`
    - [x] Update static absolute paths inside `server/main.py`, `server/deck_manager.py`, and `server/verify.py`
    - [x] Refactor `server/streamdeck.service` systemd paths
    - [x] Update `start_service.sh` to point to `server/streamdeck.service`
    - [x] Reinstall and start service via `./start_service.sh` and verify daemon status

- [x] **29. Timezone Integration for Clock Widget & Sleep Schedule**
    - [x] Add `ZoneInfo` import and robust parsing of `TIMEZONE` env variable in `server/main.py`
    - [x] Update `update_button_state` inside `server/main.py` to localize clock widget time
    - [x] Update `on_button_press` inside `server/main.py` to localize pressed clock temporary date
    - [x] Update `run_clock_daemon` loop inside `server/main.py` to localize periodic clock updates and tick sleep duration
    - [x] Update `is_within_sleep_window` inside `server/main.py` to localize screen sleep schedules
    - [x] Create `server/verify_timezone.py` testing suite to validate timezone parsing, adjustments, and system fallbacks
    - [x] Run entire verification suite (`verify.py`, `verify_sleep.py`, `verify_timezone.py`) to prove correct functionality

- [x] **30. LibreHardwareMonitor HTTP Pull Telemetry Integration**
    - [x] Create detailed implementation plan and obtain approval
    - [x] Update `config.yaml` with LHM Pull settings (`pc_monitor_mode`, `pc_monitor_ip`, `pc_monitor_port`)
    - [x] Add LHM WMI JSON recursive parsing function in `server/main.py`
    - [x] Implement `run_pc_monitor_pull_daemon` thread in `server/main.py` (fetching `data.json` over HTTP GET)
    - [x] Remove old UDP listener sockets and threads from `server/main.py`
    - [x] Update testing suite inside `server/verify.py` to assert LHM config options and mock parsing calculations
    - [x] Run entire verification test suite (`verify.py`, `verify_sleep.py`, `verify_timezone.py`) to confirm zero regressions

## Results & Review

### Implementation Summary
*   **Modular Architecture:** Successfully created a robust, decoupled integration for Ulanzi D200 Stream Deck controllers and Philips Hue REST APIs.
*   **Simulator Mode:** Fully operational Simulator Mode featuring a console CLI and real-time button renders saved as PNG files (196x196 pixels RGB).
*   **Clock Widget & Timezone support:** Background Clock Widget Daemon using real-time timezone configuration with elegant fallback options.
*   **Weather Widgets ("weather" & "weather+1"):** High-contrast weather rendering supporting auto cache invalidate and tap force refresh.
*   **Screen Auto Sleep & Wake:** Automatically shuts down buttons LCD screens on customizable schedule and inactivity timeout, seamlessly waking up on physical tap and consuming the initial keypress.
*   **LibreHardwareMonitor HTTP Pull Telemetry:** Transitioned Windows resource monitor widgets to an HTTP Pull architecture. The Linux daemon queries LHM's integrated web API (`/data.json`) every 5 seconds, using a recursive path-based parser with robust vendor keywords (Intel, AMD, NVIDIA, Ryzen, Radeon, SSD, RAM) to map metrics flawlessly without Windows-side scripting dependencies, incorporating automatic offline detection.

### Test Results (`verify.py`)
```text
============================================================
          STARTING AUTOMATED VERIFICATION SUITE
============================================================
Testing config.yaml safety and parsing...
✅ config.yaml safety validation passed successfully.
------------------------------------------------------------
Testing HueController simulation and toggles...
2026-05-25 23:23:25,872 [INFO] HueController: Initialized in SIMULATOR MODE. No network requests will be made.
2026-05-25 23:23:25,872 [INFO] HueController: Toggling Device 1 -> OFF
2026-05-25 23:23:25,872 [INFO] HueController (SIM): Updated Light 1 state -> {'on': False}
2026-05-25 23:23:25,872 [INFO] HueController: Toggling Device 3 -> ON
2026-05-25 23:23:25,872 [INFO] HueController (SIM): Updated Light 3 state -> {'on': True}
✅ HueController simulation checks passed successfully.
------------------------------------------------------------
Testing DeckManager image rendering output...
2026-05-25 23:23:25,872 [INFO] DeckManager: Initialized in SIMULATOR MODE. Generated images will be saved to output_sim/
2026-05-25 23:23:25,882 [INFO] DeckManager (SIM): Saved button 9 screen to -> /home/zee/code/streamdeck/server/output_sim/button_9.png
2026-05-25 23:23:25,884 [INFO] DeckManager (SIM): Saved button 8 screen to -> /home/zee/code/streamdeck/server/output_sim/button_8.png
2026-05-25 23:23:25,887 [INFO] DeckManager (SIM): Saved button 7 screen to -> /home/zee/code/streamdeck/server/output_sim/button_7.png
2026-05-25 23:23:25,890 [INFO] DeckManager (SIM): Saved button 6 screen to -> /home/zee/code/streamdeck/server/output_sim/button_6.png
2026-05-25 23:23:25,892 [INFO] DeckManager (SIM): Saved button 5 screen to -> /home/zee/code/streamdeck/server/output_sim/button_5.png
✅ DeckManager image rendering output checked successfully.
------------------------------------------------------------
Testing WeatherService logic and aggregation...
2026-05-25 23:23:25,912 [INFO] WeatherService: Operating in MOCK mode (No valid API key). Returning premium mock forecast.
✅ WeatherService validation checks passed successfully.
------------------------------------------------------------
Testing LibreHardwareMonitor JSON search and parsing logic...
2026-05-25 23:23:25,921 [INFO] StreamDeckApp: Configured timezone: America/Sao_Paulo
2026-05-25 23:23:25,921 [INFO] StreamDeckApp: Loading configuration files...
2026-05-25 23:23:25,929 [INFO] StreamDeckApp: Successfully loaded 7 button mappings.
2026-05-25 23:23:25,929 [INFO] HueController: Initialized in SIMULATOR MODE. No network requests will be made.
2026-05-25 23:23:25,929 [INFO] DeckManager: Initialized in SIMULATOR MODE. Generated images will be saved to output_sim/
✅ LibreHardwareMonitor JSON search and parsing logic check passed.
============================================================
🎉 ALL VERIFICATION SUITE CHECKS COMPLETED SUCCESSFULLY!
============================================================
```
