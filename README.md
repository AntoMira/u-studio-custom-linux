# Custom Ulanzi D200 Stream Deck + Philips Hue Integration

This project is a highly customizable, local Python-based controller for the **Ulanzi D200 Stream Controller**, integrating directly with your local **Philips Hue REST API**. It allows the physical tactile LCD keys of the D200 to:
1.  Toggle Philips Hue lights and smart plugs.
2.  Adjust light brightness.
3.  Display real-time states ("ON", "OFF", brightness %) dynamically drawn over custom PNG icons.
4.  Render a background digital clock widget ("HH:MM") updating in real time.

For developers and off-grid testing, the application includes a robust **Simulator Mode** that allows you to emulates button clicks from your console and writes visual screens directly to a local directory for preview.

---

## 🛠️ Setup Instructions

### 1. Environment and Packages
This project is built using Python 3.9+. Follow these steps to configure your local virtual environment:

```bash
# Navigate to the workspace
cd /home/zee/code/streamdeck

# Initialize virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

---

### 2. Philips Hue Bridge Configuration
To control your lights, you need to configure the local network bridge connection.

1.  **Find your Hue Bridge IP Address:** You can find it on your router's client list or via `https://discovery.meethue.com`.
2.  **Generate a Developer Username (API Key):**
    *   Press the physical link button in the center of your **Hue Bridge**.
    *   Within 30 seconds, run the following `curl` command in your terminal, replacing `<BRIDGE_IP>` with your bridge's IP:
    ```bash
    curl -X POST -H "Content-Type: application/json" \
         -d '{"devicetype":"ulanzi_streamdeck#linux"}' \
         http://<BRIDGE_IP>/api
    ```
    *   The bridge will return a JSON response containing a generated `username` string (this is your API Key). Keep this private.

---

### 3. Environment Secrets (.env)
Create a `.env` file in the root of the project by copying the example:

```bash
cp .env.example .env
```

Edit the `.env` file and input your settings:
```env
HUE_BRIDGE_IP=192.168.1.100
HUE_USERNAME=your_generated_api_username
SIMULATOR_MODE=True  # Set to False to communicate with physical D200 hardware
```

---

### 4. Customizing Mappings (config.yaml)
Edit `config.yaml` to map keys to your home automation devices:
*   `index`: Key index (from 0 to 12).
*   `device_type`: `light` (dimmable bulb), `plug` (on/off plug), or `widget` (time widget).
*   `action_type`: `hue_toggle` or `clock`.
*   `target`: Your Philips Hue light/plug ID (numeric string).
*   `label`: Friendly name displayed on top of the button.
*   `icon`: Relative path to a PNG icon inside your project. (If missing, the script falls back to drawing beautiful minimal geometric vector shapes).

---

### 5. USB Permissions on Linux (udev Rules)
To run this application as a non-root user (without `sudo`), you must grant your user permissions to access the D200 USB device.

1.  Plug in your D200 via USB.
2.  Run `lsusb` in your terminal to find the device's Vendor ID and Product ID:
    ```bash
    lsusb
    # Example output showing: Bus 001 Device 004: ID 2207:0018
    # 2207 is the Vendor ID (idVendor), 0018 is the Product ID (idProduct)
    ```
3.  Create a custom udev rule:
    ```bash
    sudo nano /etc/udev/rules.d/99-ulanzi-d200.rules
    ```
4.  Add the following line, replacing `2207` and `0018` with the actual Vendor/Product IDs from `lsusb`:
    ```udev
    SUBSYSTEMS=="usb", ATTRS{idVendor}=="2207", ATTRS{idProduct}=="0018", MODE="0666", GROUP="plugdev"
    ```
5.  Reload the udev rules:
    ```bash
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    ```

---

## 🚀 Running the Application

### Verification Suite
Run the automated test suite to verify configuration formatting, Pillow image drawing, and mock API toggling:
```bash
python verify.py
```

### Main Application
Run the Stream Deck application:
```bash
python main.py
```

#### Console Keyboard Interface (Simulator Mode)
When `SIMULATOR_MODE=True` is enabled, the program launches an interactive console. 
*   **Trigger Keypress:** Type any mapped button index (e.g., `0`, `1`, `2`) and press `Enter` to simulate physical button clicks!
*   **Preview Renderings:** Check the `/home/zee/code/streamdeck/output_sim/` directory. You will see visual files like `button_0.png` updating dynamically to show exactly what would render on the physical LCD screens!
*   **Clock interaction:** Clicking the clock key temporarily renders the current Date (`DD/MM`) for 3 seconds before automatically reverting to time (`HH:MM`).
*   **Quit:** Type `q`, `exit`, or press `Ctrl+C` to shut down gracefully.
