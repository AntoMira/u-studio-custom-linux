import os
import sys
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
        assert 0 <= btn["index"] <= 12, f"Button index {btn['index']} out of range (0-12)"
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
