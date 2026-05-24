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

## Results & Review

### Implementation Summary
*   **Modular Architecture:** Successfully created a robust, decoupled integration for Ulanzi D200 Stream Deck controllers and Philips Hue REST APIs.
*   **Simulator Mode:** Fully operational Simulator Mode featuring a console CLI and real-time button renders saved as PNG files (196x196 pixels RGB).
*   **Clock Daemon:** Real-time clock widget background thread completed and verified.
*   **Version Control:** Initialized Git repository, renamed default branch to `main`, successfully created a new private repository on GitHub (`AntoMira/streamdeck`) using `gh` CLI, and pushed all commits with remote tracking fully functional.
*   **Venv Runner Script (`run.sh`):** Created and verified a self-contained runner script that automatically bootstraps the virtual environment, installs dependencies, and cleanly boots up the interactive Stream Deck simulator environment.
*   **Python 3.9 & Physical Hardware Connection:** Upgraded system environment to Python 3.9, resolved undeclared `deepdiff` dependencies in PyPI, successfully established physical communication with the Ulanzi D200 Stream Deck via `hidapi` packets, and removed import fallbacks to enforce physical mode hardware constraints.
*   **Small Screen Clock Sync:** Integrated a background asyncio-scheduled keep-alive loop that automatically updates the D200's small information status screen with a high-precision, timezone-configurable real-time clock, successfully matching local time outputs.
*   **Global Font Size Customization:** Implemented root-level properties (`font_size_label` and `font_size_status`) in `config.yaml` to dynamically customize Pillow-rendered text sizes on the physical D200 buttons.
*   **Config Documentation:** Added extensive inline comments documenting every single global setting and button configuration attribute with expected formats and valid ranges.
*   **Widget UI Border Polish:** Modified `deck_manager.py` to selectively disable outer borders (outlines) for borders on buttons set to `device_type: "widget"`, successfully removing the blue margin around the clock widget while preserving the light blue text and clock dial highlights.
*   **Philips Hue Device Listing Tool:** Created `list_hue.py` CLI utility and a shell wrapper script `list_hue.sh` allowing quick physical/simulator connection checks and device ID listings.
*   **Periodic State Synchronization Daemon:** Implemented a background thread `run_state_sync_daemon` in `main.py` that polls the Hue Bridge every 5 seconds via `list_devices()` and automatically refreshes all button states if any external changes are detected, reducing HTTP overhead to a single GET call per tick.
*   **Configurable Background Polling:** Added root-level configuration option `state_sync_interval` to `config.yaml` to dynamically customize the sleep duration of the device state sync daemon thread, fully integrated in `main.py` and validated via automated unit testing.
*   **Firmware Cache Invalidation:** Implemented a timestamp-salted cache-busting filename mechanism for button icons inside `deck_manager.py` to bypass Ulanzi D200 hardware-level image caching, combined with automatic local cleanup of older icon assets.
*   **Dynamic Status Colors (Green/Red/Gray):** Refactored `update_button()` in `deck_manager.py` to accept a `reachable` parameter and render dynamic, premium visual themes: active state (ON) renders status text in **green**, inactive state (OFF) renders status and borders in **red**, and unreachable/disconnected state (OFFLINE) renders text and borders in **gray**.

### Test Results (`verify.py`)
```text
============================================================
          STARTING AUTOMATED VERIFICATION SUITE
============================================================
Testing config.yaml safety and parsing...
✅ config.yaml safety validation passed successfully.
------------------------------------------------------------
Testing HueController simulation and toggles...
2026-05-24 20:02:43,028 [INFO] HueController: Initialized in SIMULATOR MODE. No network requests will be made.
2026-05-24 20:02:43,029 [INFO] HueController: Toggling Device 1 -> OFF
2026-05-24 20:02:43,029 [INFO] HueController (SIM): Updated Light 1 state -> {'on': False}
2026-05-24 20:02:43,029 [INFO] HueController: Toggling Device 3 -> ON
2026-05-24 20:02:43,029 [INFO] HueController (SIM): Updated Light 3 state -> {'on': True}
✅ HueController simulation checks passed successfully.
------------------------------------------------------------
Testing DeckManager image rendering output...
2026-05-24 20:02:43,029 [INFO] DeckManager: Initialized in SIMULATOR MODE. Generated images will be saved to output_sim/
2026-05-24 20:02:43,043 [INFO] DeckManager (SIM): Saved button 9 screen to -> /home/zee/code/streamdeck/output_sim/button_9.png
✅ DeckManager image rendering output checked successfully.
============================================================
🎉 ALL VERIFICATION SUITE CHECKS COMPLETED SUCCESSFULLY!
============================================================
```
