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
- [/] **6. Verification Suite**
    - [x] Create `verify.py` with unit tests for config formatting, Pillow dimensions, and mock APIs
    - [ ] Manually verify image renderings and toggling behavior in `output_sim/`
- [x] **7. Documentation**
    - [x] Create `README.md` with setup steps, Hue API token extraction guide, and Linux udev USB rules
- [ ] **8. Version Control & GitHub**
    - [ ] Initialize Git repository (`git init`)
    - [ ] Commit initial project files (`git commit`)
    - [ ] Create remote repository on GitHub using `gh` CLI (`gh repo create`)
    - [ ] Push to main branch (`git push`) and verify pull/fetch (`git pull`)

## Results & Review
*(To be populated upon completion)*
