import os
import sys
import time
import yaml
from PIL import Image

from hue_controller import HueController
from deck_manager import DeckManager
from weather_service import WeatherService

def test_config_parsing():
    """
    Validates that config.yaml exists, parses safely, and conforms to expectations.
    """
    print("Testing config.yaml safety and parsing...")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.yaml")
    assert os.path.exists(config_path), f"config.yaml not found at {config_path}"
    
    with open(config_path, "r") as f:
        # Verify safe loading does not raise exceptions
        config = yaml.safe_load(f)
        
    assert "buttons" in config, "Missing 'buttons' root in config.yaml"
    buttons = config["buttons"]
    assert len(buttons) > 0, "No buttons configured in config.yaml"
    
    for btn in buttons:
        assert "index" in btn, "Button config is missing 'index' key"
        # 0-12 are the keys; 13 is the wide info screen (weather_panel / weather_graph)
        assert 0 <= btn["index"] <= 13, f"Button index {btn['index']} out of range (0-13)"
        if btn["index"] == 13:
            assert btn.get("action_type") in ("weather_panel", "weather_graph"), "Index 13 (wide info screen) only supports weather_panel / weather_graph"
        assert "device_type" in btn, "Button config is missing 'device_type' key"
        assert btn["device_type"] in ("light", "plug", "widget"), f"Unsupported device_type: {btn['device_type']}"
        assert "action_type" in btn, "Button config is missing 'action_type' key"
        
    assert "margin_label" in config, "Missing 'margin_label' root in config.yaml"
    assert isinstance(config["margin_label"], int), "margin_label must be an integer"
    assert "margin_status" in config, "Missing 'margin_status' root in config.yaml"
    assert isinstance(config["margin_status"], int), "margin_status must be an integer"
    assert "small_window_mode" in config, "Missing 'small_window_mode' root in config.yaml"
    assert isinstance(config["small_window_mode"], int), "small_window_mode must be an integer"
    assert "state_sync_interval" in config, "Missing 'state_sync_interval' root in config.yaml"
    assert isinstance(config["state_sync_interval"], int), "state_sync_interval must be an integer"
    assert config["state_sync_interval"] > 0, "state_sync_interval must be a positive integer greater than 0"
    # Verify pc_monitor button attributes
    pc_buttons = [b for b in buttons if b.get("action_type") == "pc_monitor"]
    assert len(pc_buttons) > 0, "Expected at least one pc_monitor button configured"
    for b in pc_buttons:
        if "mode" in b:
            assert b["mode"] in ("pull", "push"), "Button mode must be 'pull' or 'push'"
        if "port" in b:
            assert isinstance(b["port"], int) and 1 <= b["port"] <= 65535, "Button port must be valid"
        if "sync_interval" in b:
            assert isinstance(b["sync_interval"], int) and b["sync_interval"] > 0, "Button sync_interval must be > 0"

    assert "button_debounce_seconds" in config, "Missing 'button_debounce_seconds' root in config.yaml"
    assert isinstance(config["button_debounce_seconds"], (int, float)), "button_debounce_seconds must be a number"
    assert config["button_debounce_seconds"] > 0, "button_debounce_seconds must be positive"

    assert "mqtt" in config, "Missing 'mqtt' section in config.yaml"
    assert isinstance(config["mqtt"].get("port", 1883), int), "MQTT port must be an integer"

    print("✅ config.yaml safety validation passed successfully.")

def test_hue_controller_simulation():
    """
    Validates HueController mock behaviors.
    """
    print("Testing HueController simulation and toggles...")
    controller = HueController(bridge_ip="127.0.0.1", username="test", simulator_mode=True)
    
    # Test initial states
    state = controller.get_light_state("1")
    assert state["on"] is True, "Light 1 expected to be ON initially"
    assert state["bri"] == 254, "Light 1 expected to have full brightness initially"
    
    # Test toggle action
    success = controller.toggle_light("1")
    assert success is True, "Light 1 toggle failed"
    
    new_state = controller.get_light_state("1")
    assert new_state["on"] is False, "Light 1 should be OFF after toggle"
    
    # Test plug device (which has no brightness)
    plug_state = controller.get_light_state("3")
    assert plug_state["on"] is False, "Plug 3 expected to be OFF initially"
    assert plug_state["bri"] is None, "Plug 3 should not have a brightness attribute"
    
    success = controller.toggle_light("3")
    assert success is True, "Plug 3 toggle failed"
    assert controller.get_light_state("3")["on"] is True, "Plug 3 should be ON after toggle"
    
    print("✅ HueController simulation checks passed successfully.")

def test_deck_manager_rendering():
    """
    Validates that PIL creates properly formatted 196x196 PNG files.
    """
    print("Testing DeckManager image rendering output...")
    manager = DeckManager(simulator_mode=True)
    
    test_btn_offline_idx = 5
    test_ceiling_idx = 3
    test_lamp_idx = 6
    test_printer_idx = 4

    # Render test 3-bar GPU monitor button (RTX 5080)
    manager.update_button(
        index=7,
        label="RTX 5080",
        device_type="widget",
        is_on=True,
        reachable=True,
        cpu_pct=65.0,
        mem_pct=52.0,
        temp_val=58.0,
        col_labels=("GPU", "RAM", "TMP")
    )

    # Render test 3-bar monitor button for PC Gamer (remote)
    manager.update_button(
        index=8,
        label="PC Gamer",
        device_type="widget",
        is_on=True,
        reachable=True,
        cpu_pct=78.0,
        mem_pct=45.0,
        temp_val=68.0
    )
    
    # Render test 3-bar monitor button for Servidor (localhost)
    manager.update_button(
        index=9,
        label="Servidor",
        device_type="widget",
        is_on=True,
        reachable=True,
        cpu_pct=25.0,
        mem_pct=52.0,
        temp_val=41.0
    )
    
    # Render ceiling test button
    test_ceiling_idx = 1
    manager.update_button(
        index=test_ceiling_idx,
        label="Ceiling Light",
        device_type="light",
        is_on=True,
        brightness=75,
        icon_path="ceiling",
        reachable=True
    )

    # Render lamp test button
    test_lamp_idx = 6
    manager.update_button(
        index=test_lamp_idx,
        label="Desk Lamp",
        device_type="light",
        is_on=True,
        brightness=50,
        icon_path="lamp",
        reachable=True
    )

    # Render 3dprinter test button
    test_printer_idx = 5
    manager.update_button(
        index=test_printer_idx,
        label="3D Printer",
        device_type="plug",
        is_on=True,
        icon_path="3dprinter",
        reachable=True
    )
    
    # Render weather gradient test button (cold weather)
    test_weather_cold_idx = 4
    manager.update_button(
        index=test_weather_cold_idx,
        label="Cold Day",
        device_type="widget",
        is_on=True,
        text_override="-3°/1°",
        weather_type="snow",
        min_temp=-3.0,
        max_temp=1.0
    )

    # Render weather gradient test button (hot weather)
    test_weather_hot_idx = 3
    manager.update_button(
        index=test_weather_hot_idx,
        label="Hot Day",
        device_type="widget",
        is_on=True,
        text_override="29°/35°",
        weather_type="clear",
        min_temp=29.0,
        max_temp=35.0
    )

    # Render PC performance monitoring widgets to test geometry layouts
    for shape in ("pc_monitor", "cpu", "gpu", "ram", "disk"):
        manager.update_button(
            index=2,
            label="MY-PC",
            device_type="widget",
            is_on=True,
            icon_path=shape,
            text_override=f"{shape.upper()}: 50%"
        )
        target_path = os.path.join(manager.output_sim_dir, f"button_2.png")
        assert os.path.exists(target_path), f"Simulated {shape} button image not saved"
    
    # Verify button image file creation
    test_btn_idx = 9
    target_path = os.path.join(manager.output_sim_dir, f"button_{test_btn_idx}.png")
    assert os.path.exists(target_path), f"Simulated button image not saved to {target_path}"
    
    # Verify image output characteristics (offline)
    target_path_offline = os.path.join(manager.output_sim_dir, f"button_{test_btn_offline_idx}.png")
    assert os.path.exists(target_path_offline), f"Simulated offline button image not saved to {target_path_offline}"

    # Verify image output characteristics (ceiling)
    target_path_ceiling = os.path.join(manager.output_sim_dir, f"button_{test_ceiling_idx}.png")
    assert os.path.exists(target_path_ceiling), f"Simulated ceiling button image not saved to {target_path_ceiling}"

    # Verify image output characteristics (lamp)
    target_path_lamp = os.path.join(manager.output_sim_dir, f"button_{test_lamp_idx}.png")
    assert os.path.exists(target_path_lamp), f"Simulated lamp button image not saved to {target_path_lamp}"

    # Verify image output characteristics (3dprinter)
    target_path_printer = os.path.join(manager.output_sim_dir, f"button_{test_printer_idx}.png")
    assert os.path.exists(target_path_printer), f"Simulated printer button image not saved to {target_path_printer}"
    
    # Verify image output characteristics (cold weather gradient)
    target_path_cold = os.path.join(manager.output_sim_dir, f"button_{test_weather_cold_idx}.png")
    assert os.path.exists(target_path_cold), f"Simulated cold weather button image not saved to {target_path_cold}"

    # Verify image output characteristics (hot weather gradient)
    target_path_hot = os.path.join(manager.output_sim_dir, f"button_{test_weather_hot_idx}.png")
    assert os.path.exists(target_path_hot), f"Simulated hot weather button image not saved to {target_path_hot}"

    with Image.open(target_path_cold) as img:
        assert img.size == (196, 196), f"Wrong dimensions: {img.size}, expected (196, 196)"
        assert img.format == "PNG", f"Wrong format: {img.format}, expected PNG"
        assert img.mode == "RGB", f"Wrong mode: {img.mode}, expected RGB"
        
    print("✅ DeckManager image rendering output checked successfully.")

def test_weather_service():
    """
    Validates WeatherService aggregation, priorities, and mock structures.
    """
    print("Testing WeatherService logic and aggregation...")
    service = WeatherService(api_key="", city="Sao Paulo,BR")
    assert service.is_mock_mode() is True, "WeatherService should run in mock mode when API key is empty"
    
    # Test priority mapping
    w_type, priority = service.get_weather_type_and_priority(201)
    assert w_type == "thunderstorm" and priority == 5
    
    w_type, priority = service.get_weather_type_and_priority(800)
    assert w_type == "clear" and priority == 0
    
    w_type, priority = service.get_weather_type_and_priority(501)
    assert w_type == "rain" and priority == 4

    # Test aggregate helper
    records = [
        {"main": {"temp_min": 15.0, "temp_max": 20.0}, "weather": [{"id": 800}]},  # clear
        {"main": {"temp_min": 14.0, "temp_max": 22.0}, "weather": [{"id": 500}]},  # rain
        {"main": {"temp_min": 16.0, "temp_max": 18.0}, "weather": [{"id": 801}]},  # clouds
    ]
    res = service._aggregate_day_records(records)
    assert res["min_temp"] == 14.0, "Aggregated min temperature should be the minimum over all records"
    assert res["max_temp"] == 22.0, "Aggregated max temperature should be the maximum over all records"
    assert res["type"] == "rain", "Aggregated predominant type should prioritize severe/rain over clear/clouds"
    
    # Test mock forecast retrieval
    data = service.get_weather_data()
    assert "weather" in data and "weather_forecast" in data and "weather_forecast+1" in data, "Weather data structure is missing keys"
    assert data["weather"]["type"] == "clouds"
    assert data["weather_forecast"]["type"] == "clear"
    assert data["weather_forecast+1"]["type"] == "rain"
    
    print("✅ WeatherService validation checks passed successfully.")

def test_lhm_telemetry_parsing():
    """
    Validates the recursive search and parser calculations for the LibreHardwareMonitor JSON tree.
    """
    print("Testing LibreHardwareMonitor JSON search and parsing logic...")
    
    # 1. Create a dummy LHM sensor tree structure
    dummy_tree = {
        "Text": "SensorTree",
        "Children": [
            {
                "Text": "DESKTOP-ABC1234",
                "Children": [
                    {
                        "Text": "Intel Core i9-13900K",
                        "Children": [
                            {
                                "Text": "Temperatures",
                                "Children": [
                                    {"Text": "CPU Package", "Value": "62.5 °C", "Children": []},
                                    {"Text": "CPU Core #1", "Value": "55.0 °C", "Children": []}
                                ]
                            },
                            {
                                "Text": "Load",
                                "Children": [
                                    {"Text": "CPU Total", "Value": "42.3 %", "Children": []}
                                ]
                            }
                        ]
                    },
                    {
                        "Text": "NVIDIA GeForce RTX 4090",
                        "Children": [
                            {
                                "Text": "Temperatures",
                                "Children": [
                                    {"Text": "GPU Core", "Value": "50,2 °C", "Children": []}
                                ]
                            },
                            {
                                "Text": "Load",
                                "Children": [
                                    {"Text": "GPU Core", "Value": "85.0 %", "Children": []}
                                ]
                            }
                        ]
                    },
                    {
                        "Text": "Generic Memory",
                        "Children": [
                            {
                                "Text": "Load",
                                "Children": [
                                    {"Text": "Memory", "Value": "64.1 %", "Children": []}
                                ]
                            }
                        ]
                    },
                    {
                        "Text": "SanDisk SSD 1TB",
                        "Children": [
                            {
                                "Text": "Load",
                                "Children": [
                                    {"Text": "Used Space", "Value": "78.9 %", "Children": []}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    
    import os
    import fcntl
    fcntl.flock = lambda fd, op: None
    os.environ["SIMULATOR_MODE"] = "True"
    
    from main import StreamDeckApp
    app = StreamDeckApp()
    
    # 2. Test PC Name extraction
    pc_name = dummy_tree.get("Text", "PC")
    if pc_name == "SensorTree" and dummy_tree.get("Children"):
        pc_name = dummy_tree["Children"][0].get("Text", "PC")
    assert pc_name == "DESKTOP-ABC1234", f"PC name should be DESKTOP-ABC1234, got {pc_name}"
    
    # 3. Test CPU Package Temp paths
    cpu_temp_paths = [
        ["intel", "temperatures", "cpu package"],
        ["cpu", "temperatures", "core max"],
    ]
    raw_val = app.get_sensor_value(dummy_tree, cpu_temp_paths)
    assert raw_val == "62.5 °C", f"Expected '62.5 °C', got '{raw_val}'"
    parsed_val = app.parse_lhm_value(raw_val)
    assert parsed_val == 62.5, f"Expected 62.5, got {parsed_val}"
    
    # 4. Test CPU Total Load paths
    cpu_usage_paths = [
        ["intel", "load", "cpu total"],
    ]
    raw_val = app.get_sensor_value(dummy_tree, cpu_usage_paths)
    assert raw_val == "42.3 %", f"Expected '42.3 %', got '{raw_val}'"
    parsed_val = app.parse_lhm_value(raw_val)
    assert parsed_val == 42.3, f"Expected 42.3, got {parsed_val}"
    
    # 5. Test GPU Temp paths with decimal comma formatting
    gpu_temp_paths = [
        ["nvidia", "temperatures", "gpu core"],
    ]
    raw_val = app.get_sensor_value(dummy_tree, gpu_temp_paths)
    assert raw_val == "50,2 °C", f"Expected '50,2 °C', got '{raw_val}'"
    parsed_val = app.parse_lhm_value(raw_val)
    assert parsed_val == 50.2, f"Expected 50.2, got {parsed_val}"
    
    # 6. Test RAM Load paths
    ram_usage_paths = [
        ["generic memory", "load", "memory"],
    ]
    raw_val = app.get_sensor_value(dummy_tree, ram_usage_paths)
    assert raw_val == "64.1 %", f"Expected '64.1 %', got '{raw_val}'"
    parsed_val = app.parse_lhm_value(raw_val)
    assert parsed_val == 64.1, f"Expected 64.1, got {parsed_val}"
    
    # 7. Test Disk Load paths
    disk_usage_paths = [
        ["ssd", "load", "used space"],
    ]
    raw_val = app.get_sensor_value(dummy_tree, disk_usage_paths)
    assert raw_val == "78.9 %", f"Expected '78.9 %', got '{raw_val}'"
    parsed_val = app.parse_lhm_value(raw_val)
    assert parsed_val == 78.9, f"Expected 78.9, got {parsed_val}"
    
    print("✅ LibreHardwareMonitor JSON search and parsing logic check passed.")

def test_mqtt_and_tasmota_rendering():
    """
    Validates Tasmota MQTT payload parsing and thermometer widget image rendering.
    """
    print("Testing Tasmota MQTT payload parsing and thermometer widget rendering...")
    from mqtt_service import parse_tasmota_payload

    # 1. Test nested Tasmota AM2301 payload
    payload1 = '{"Time":"2026-09-22T20:00:00","AM2301":{"Temperature":24.5,"Humidity":52.0},"TempUnit":"C"}'
    res1 = parse_tasmota_payload(payload1)
    assert res1["temperature"] == 24.5, f"Expected temperature 24.5, got {res1['temperature']}"
    assert res1["humidity"] == 52.0, f"Expected humidity 52.0, got {res1['humidity']}"

    # 2. Test flat JSON payload
    payload2 = '{"Temperature": 19.8, "Humidity": 65.0}'
    res2 = parse_tasmota_payload(payload2)
    assert res2["temperature"] == 19.8, f"Expected temperature 19.8, got {res2['temperature']}"
    assert res2["humidity"] == 65.0, f"Expected humidity 65.0, got {res2['humidity']}"

    # 3. Test raw float payload fallback
    payload3 = '22.3'
    res3 = parse_tasmota_payload(payload3)
    assert res3["temperature"] == 22.3, f"Expected temperature 22.3, got {res3['temperature']}"

    # 4. Test Tasmota ENERGY telemetry payload
    payload4 = '{"Time":"2026-09-22T20:25:00","ENERGY":{"Total":12.3,"Power":150,"Voltage":220,"Current":0.68}}'
    res4 = parse_tasmota_payload(payload4)
    assert res4["power"] == 150.0, f"Expected power 150.0, got {res4['power']}"
    assert res4["current"] == 0.68, f"Expected current 0.68, got {res4['current']}"

    # 5. Render temperature widget button image (large temp in center, humidity at bottom)
    manager = DeckManager(simulator_mode=True)
    manager.update_button(
        index=9,
        label="Sala",
        device_type="widget",
        is_on=True,
        icon_path="none",
        center_text="24.5°C",
        text_override="52%",
        min_temp=24.5
    )

    # 6. Render tasmota_power widget button image (large power in center, current in amperes at bottom, left vertical power bar)
    manager.update_button(
        index=8,
        label="Tomada",
        device_type="widget",
        is_on=True,
        icon_path="none",
        center_text="150 W",
        text_override="0.68A",
        power_val=150.0,
        max_power=1000.0,
        reachable=True
    )

    out_path = os.path.join(manager.output_sim_dir, "button_8.png")
    assert os.path.exists(out_path), f"Expected button_8.png at {out_path}"
    img = Image.open(out_path)
    assert img.size == (196, 196), f"Expected 196x196 image size, got {img.size}"

    print("✅ Tasmota MQTT payload parsing (temp, humidity, power, current) and widget rendering checks passed successfully.")

def test_button_debounce():
    """
    Validates button debouncing logic on DeckManager:
    - Rapid consecutive presses on the same button are dropped.
    - Presses on different buttons are allowed independently.
    - Presses after debounce duration expires are processed.
    - Hardware key release (pressed=False) events do not trigger callbacks.
    - Wake-up keypress does not trigger actions, and immediate chatter after wake-up is debounced.
    """
    print("Testing button debouncer logic on DeckManager...")
    manager = DeckManager(simulator_mode=True, debounce_seconds=0.35)
    
    clicks = []
    manager.register_callback(lambda idx: clicks.append(idx))

    # 1. Initial simulated press on button 1
    res1 = manager.simulate_press(1)
    assert res1 is True, "First simulated press should succeed"
    assert clicks == [1], f"Expected clicks to be [1], got {clicks}"

    # 2. Immediate second press on button 1 (bounce / double click simulation)
    res2 = manager.simulate_press(1)
    assert res2 is False, "Immediate second press on the same button must be debounced"
    assert clicks == [1], f"Clicks should still be [1], got {clicks}"

    # 3. Immediate press on a DIFFERENT button (button 2) should NOT be blocked
    res3 = manager.simulate_press(2)
    assert res3 is True, "Press on a different button should not be blocked by debounce of another button"
    assert clicks == [1, 2], f"Expected clicks to be [1, 2], got {clicks}"

    # 4. Immediate second press on button 2 should be debounced
    res4 = manager.simulate_press(2)
    assert res4 is False, "Immediate second press on button 2 must be debounced"
    assert clicks == [1, 2], f"Clicks should still be [1, 2], got {clicks}"

    # 5. Subsequent press on button 1 after elapsed debounce time
    manager.last_press_time[1] = time.time() - 0.5  # Simulate 500ms elapsed
    res5 = manager.simulate_press(1)
    assert res5 is True, "Press on button 1 after debounce window should succeed"
    assert clicks == [1, 2, 1], f"Expected clicks to be [1, 2, 1], got {clicks}"

    # 6. Force press bypasses debounce check
    res6 = manager.simulate_press(1, force=True)
    assert res6 is True, "Forced press should bypass debounce check"
    assert clicks == [1, 2, 1, 1], f"Expected clicks to be [1, 2, 1, 1], got {clicks}"

    # 7. Hardware keypress handler tests
    manager.reset_debounce()
    clicks.clear()

    # Key release should be ignored completely
    manager._on_hardware_keypress(3, pressed=False)
    assert len(clicks) == 0, "Key release (pressed=False) should not trigger any callback"

    # Hardware key press down
    manager._on_hardware_keypress(3, pressed=True)
    assert clicks == [3], f"Expected [3], got {clicks}"

    # Immediate hardware chatter on key 3
    manager._on_hardware_keypress(3, pressed=True)
    assert clicks == [3], f"Immediate hardware key chatter should be debounced, got {clicks}"

    # 8. Wake-up contact chatter protection
    wake_calls = []
    manager.register_wake_callback(lambda: wake_calls.append(True))
    manager.screen_on = False
    manager.reset_debounce()
    clicks.clear()

    # Button press while screen is asleep -> should wake screen, NOT fire button callback
    manager._on_hardware_keypress(5, pressed=True)
    assert manager.screen_on is True, "Screen should be woken up"
    assert len(wake_calls) == 1, "Wake callback should be called"
    assert len(clicks) == 0, "Button action should NOT be executed when waking screen"

    # Contact chatter 50ms later while screen is now awake
    manager._on_hardware_keypress(5, pressed=True)
    assert len(clicks) == 0, "Contact chatter after wake-up MUST be debounced"

    # Intentional click after debounce window
    manager.last_press_time[5] = time.time() - 0.5
    manager._on_hardware_keypress(5, pressed=True)
    assert clicks == [5], f"Deliberate click on button 5 after wake-up should trigger action, got {clicks}"

    print("✅ Button debouncer logic verification passed successfully.")

def test_long_press():
    """
    Validates long press on DeckManager:
    - Hold reaching the threshold fires the long callback once, and release does not fire a short click.
    - Release before the threshold fires the short click only.
    - Buttons without long press config still fire immediately on press.
    """
    print("Testing long press logic on DeckManager...")
    manager = DeckManager(simulator_mode=True, debounce_seconds=0.0)
    clicks, longs = [], []
    manager.register_callback(lambda idx: clicks.append(idx))
    manager.register_long_press_callback(lambda idx, action: longs.append((idx, action)))
    manager.set_long_press_config(4, {"off": 0.2})

    # Long hold
    manager._on_hardware_keypress(4, pressed=True)
    assert clicks == [] and longs == [], "Nothing should fire before the threshold"
    time.sleep(0.4)
    assert longs == [(4, "off")], f"Expected long press off, got {longs}"
    manager._on_hardware_keypress(4, pressed=False)
    assert clicks == [], "Release after long press must not fire a short click"

    # Short tap
    longs.clear()
    manager._on_hardware_keypress(4, pressed=True)
    manager._on_hardware_keypress(4, pressed=False)
    assert clicks == [4], f"Short tap should fire click on release, got {clicks}"
    time.sleep(0.4)
    assert longs == [], "Cancelled long press timer must not fire"

    # Button without long press fires on press
    clicks.clear()
    manager._on_hardware_keypress(2, pressed=True)
    assert clicks == [2], "Button without long press config must fire immediately on press"
    manager._on_hardware_keypress(2, pressed=False)
    assert clicks == [2], "Release must not fire again"

    print("✅ Long press logic verification passed successfully.")

def test_hardware_reconnect():
    """
    Validates D200 reconnection on DeckManager (hardware mode with a fake USB device):
    - A missing device is retried with a sleep between attempts (no busy loop).
    - A device lost mid-session is dropped and reconnected when it reappears, re-sending the button page.
    - Key events from the reconnected device still reach callbacks.
    """
    print("Testing D200 hardware reconnect logic on DeckManager...")
    import asyncio
    try:
        import strmdck.device_manager as dm
    except ImportError:
        print("⚠️ strmdck not installed in this interpreter (use venv/bin/python); skipping hardware reconnect test.")
        return

    class FakeAction:
        def __init__(self, index, pressed):
            self.index, self.pressed = index, pressed

    class FakeDevice:
        def __init__(self, events, fail_after=True):
            self.events, self.fail_after = events, fail_after
            self.closed, self.pages = False, []
        def set_label_style(self, *a, **k): pass
        def set_small_window_mode(self, *a): pass
        def restore_small_window(self): pass
        def set_brightness(self, *a): pass
        def keep_alive(self): pass
        def set_buttons(self, buttons, update_only=False): self.pages.append(dict(buttons))
        def close(self): self.closed = True
        async def read_packet(self):
            for ev in self.events:
                await asyncio.sleep(0.05)
                yield ev
            if self.fail_after:
                raise IOError("device unplugged")
            while True:
                await asyncio.sleep(0.05)

    dev1 = FakeDevice([FakeAction(3, True)])
    dev2 = FakeDevice([FakeAction(7, True)], fail_after=False)
    sequence = [None, dev1, None, dev2]
    calls = []

    def fake_auto_connect():
        calls.append(time.time())
        return sequence.pop(0) if sequence else None

    original = dm.auto_connect
    dm.auto_connect = fake_auto_connect
    try:
        manager = DeckManager(simulator_mode=False, debounce_seconds=0.0, reconnect_seconds=1)
        clicks = []
        manager.register_callback(lambda idx: clicks.append(idx))
        manager.active_buttons[0] = b"img"
        time.sleep(4.5)
    finally:
        dm.auto_connect = original

    assert clicks == [3, 7], f"Expected key events from both sessions, got {clicks}"
    assert dev1.closed, "Lost device must be closed/dropped"
    assert manager.deck is dev2, "Manager should be using the reconnected device"
    assert dev2.pages and 0 in dev2.pages[0], "Button page must be re-sent after reconnect"
    gaps = [b - a for a, b in zip(calls, calls[1:])]
    assert all(g >= 0.9 for g in gaps), f"Reconnect attempts must sleep between tries, gaps={gaps}"
    assert len(calls) == 4, f"Expected exactly 4 connect attempts, got {len(calls)}"

    print("✅ D200 hardware reconnect verification passed successfully.")

def test_hardware_icon_cache():
    """
    Validates the physical-deck icon cache: a superseded button image must survive the grace period
    (a queued USB upload may still reference it) and only be removed once it is stale.
    """
    print("Testing hardware icon cache cleanup on DeckManager...")
    try:
        import strmdck.device_manager as dm
    except ImportError:
        print("⚠️ strmdck not installed in this interpreter (use venv/bin/python); skipping icon cache test.")
        return

    original = dm.auto_connect
    dm.auto_connect = lambda: None
    try:
        manager = DeckManager(simulator_mode=False, reconnect_seconds=1)
        manager.CACHE_GRACE_MS = 1000
        manager.update_button(index=11, label="A", device_type="light", is_on=True)
        first = manager.active_buttons[11]['icon']
        time.sleep(0.01)
        manager.update_button(index=11, label="A", device_type="light", is_on=False)
        second = manager.active_buttons[11]['icon']
        assert first != second, "Each update must produce a new image file"
        first_path = os.path.join(manager.cache_dir, first)
        assert os.path.exists(first_path), "Superseded image must still exist during the grace period"

        time.sleep(1.1)
        manager.update_button(index=11, label="A", device_type="light", is_on=True)
        assert not os.path.exists(first_path), "Stale superseded image must be cleaned up"
        assert os.path.exists(os.path.join(manager.cache_dir, manager.active_buttons[11]['icon']))
        if manager._update_timer:
            manager._update_timer.cancel()
    finally:
        dm.auto_connect = original

    print("✅ Hardware icon cache cleanup verification passed successfully.")

def test_small_window_background():
    """
    Validates the info screen background: black by default, a custom image is fit to 458x196,
    and "default" keeps the factory logo (no image uploaded for the wide cell).
    """
    print("Testing small window background on DeckManager...")
    try:
        import strmdck.device_manager as dm
    except ImportError:
        print("⚠️ strmdck not installed in this interpreter (use venv/bin/python); skipping small window background test.")
        return

    import tempfile
    original = dm.auto_connect
    dm.auto_connect = lambda: None
    try:
        idx = DeckManager.SMALL_WINDOW_INDEX
        m = DeckManager(simulator_mode=False, reconnect_seconds=1)
        entry = m.active_buttons[idx]
        assert entry and entry['icon'] == DeckManager.SMALL_WINDOW_BG_NAME, "Default must upload a background image"
        img = Image.open(os.path.join(m.cache_dir, entry['icon']))
        assert img.size == (458, 196) and img.getpixel((10, 10)) == (0, 0, 0), "Default background must be solid black 458x196"

        with tempfile.TemporaryDirectory() as tmp:
            custom = os.path.join(tmp, "bg.png")
            Image.new("RGB", (100, 100), (10, 20, 30)).save(custom)
            m2 = DeckManager(simulator_mode=False, reconnect_seconds=1, small_window_background=custom)
            img2 = Image.open(os.path.join(m2.cache_dir, m2.active_buttons[idx]['icon']))
            assert img2.size == (458, 196) and img2.getpixel((200, 100)) == (10, 20, 30), "Custom image must be fit to 458x196"

        m3 = DeckManager(simulator_mode=False, reconnect_seconds=1, small_window_background="default")
        assert m3.active_buttons[idx] is None if idx in m3.active_buttons else True, "'default' must keep the factory logo"
    finally:
        dm.auto_connect = original

    print("✅ Small window background verification passed successfully.")

def test_weather_panel():
    """
    Validates the wide weather panel: daily forecast parsing, 458x196 rendering for every weather type,
    and that the physical deck uploads it for the wide info screen cell.
    """
    print("Testing weather panel (daily forecast + wide render)...")
    ws = WeatherService(api_key="", city="Test")
    data = ws.get_weather_data()
    assert len(data["daily"]) >= 4, "Daily forecast must cover at least 4 days"
    assert all(k in data["daily"][0] for k in ("date", "min_temp", "max_temp", "type", "pop")), "Daily entries need date/min/max/type/pop"

    # Parse a real-shaped OpenWeather payload spanning 5 dates
    base = int(time.time())
    payload = {"list": [
        {"dt": base + h * 3600, "main": {"temp": 20, "temp_min": 15 + h % 5, "temp_max": 25 - h % 3}, "weather": [{"id": 500 if h % 7 == 0 else 800}], "pop": 0.4 if h % 7 == 0 else 0.1}
        for h in range(0, 120, 3)
    ]}
    parsed = ws._parse_forecast_data(payload)
    assert 4 <= len(parsed["daily"]) <= 5, f"Expected 4-5 daily entries, got {len(parsed['daily'])}"
    assert all(d["pop"] >= 0.1 for d in parsed["daily"]), "Daily pop must be the max of the day's entries"

    manager = DeckManager(simulator_mode=True)
    current = data["weather"]
    for wtype in ("clear", "clouds", "rain", "thunderstorm", "snow", "mist"):
        days = [dict(d, type=wtype) for d in data["daily"][1:5]]
        img = manager.render_weather_panel(dict(current, type=wtype), data["weather_forecast"], days)
        assert img.size == (458, 196), f"Panel must be 458x196, got {img.size}"
    manager.update_weather_panel(current, data["weather_forecast"], data["daily"][1:5])
    assert os.path.exists(os.path.join(manager.output_sim_dir, "weather_panel.png")), "Simulator must save weather_panel.png"

    # Weather graph: hourly series is timezone-aware and renders at the same size
    assert len(data["hourly"]) >= 24 and all("temp" in h and "rain" in h for h in data["hourly"]), "Hourly series needs temp and rain"
    parsed_hourly = parsed["hourly"]
    assert len(parsed_hourly) == len(payload["list"]) and parsed_hourly[0]["rain"] == 0.0, "Hourly series must mirror the forecast list"
    graph = manager.render_weather_graph(current, data["weather_forecast"], data["hourly"])
    assert graph.size == (458, 196), f"Graph must be 458x196, got {graph.size}"
    manager.update_weather_graph(current, data["weather_forecast"], data["hourly"])
    assert os.path.exists(os.path.join(manager.output_sim_dir, "weather_graph.png")), "Simulator must save weather_graph.png"

    try:
        import strmdck.device_manager as dm
    except ImportError:
        print("⚠️ strmdck not installed in this interpreter; skipping hardware panel upload check.")
        print("✅ Weather panel verification passed successfully.")
        return
    original = dm.auto_connect
    dm.auto_connect = lambda: None
    try:
        hw = DeckManager(simulator_mode=False, reconnect_seconds=1)
        hw.update_weather_panel(current, data["weather_forecast"], data["daily"][1:5])
        entry = hw.active_buttons[DeckManager.SMALL_WINDOW_INDEX]
        assert entry["icon"].startswith(f"button_{DeckManager.SMALL_WINDOW_INDEX}_"), "Panel must replace the wide cell image"
        assert Image.open(os.path.join(hw.cache_dir, entry["icon"])).size == (458, 196)
        if hw._update_timer:
            hw._update_timer.cancel()
    finally:
        dm.auto_connect = original

    print("✅ Weather panel verification passed successfully.")

def run_tests():
    print("="*60)
    print("          STARTING AUTOMATED VERIFICATION SUITE")
    print("="*60)
    
    try:
        test_config_parsing()
        print("-"*60)
        test_hue_controller_simulation()
        print("-"*60)
        test_deck_manager_rendering()
        print("-"*60)
        test_weather_service()
        print("-"*60)
        test_lhm_telemetry_parsing()
        print("-"*60)
        test_mqtt_and_tasmota_rendering()
        print("-"*60)
        test_button_debounce()
        print("-"*60)
        test_long_press()
        print("-"*60)
        test_hardware_reconnect()
        print("-"*60)
        test_hardware_icon_cache()
        print("-"*60)
        test_small_window_background()
        print("-"*60)
        test_weather_panel()
        print("="*60)
        print("🎉 ALL VERIFICATION SUITE CHECKS COMPLETED SUCCESSFULLY!")
        print("="*60)
        return True
    except AssertionError as e:
        print("\n❌ VERIFICATION SUITE FAILURE:")
        print(f"   AssertionError: {e}\n")
        print("="*60)
        return False

if __name__ == "__main__":
    success = run_tests()
    if not success:
        sys.exit(1)
