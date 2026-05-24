import os
import sys
import yaml
from PIL import Image

from hue_controller import HueController
from deck_manager import DeckManager

def test_config_parsing():
    """
    Validates that config.yaml exists, parses safely, and conforms to expectations.
    """
    print("Testing config.yaml safety and parsing...")
    config_path = "/home/zee/code/streamdeck/config.yaml"
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
    
    # Render test button
    test_btn_idx = 9
    manager.update_button(
        index=test_btn_idx,
        label="Test Unit",
        device_type="light",
        is_on=True,
        brightness=85,
        icon_path=None
    )
    
    # Verify image output characteristics
    target_path = os.path.join(manager.output_sim_dir, f"button_{test_btn_idx}.png")
    assert os.path.exists(target_path), f"Simulated button image not saved to {target_path}"
    
    with Image.open(target_path) as img:
        assert img.size == (196, 196), f"Wrong dimensions: {img.size}, expected (196, 196)"
        assert img.format == "PNG", f"Wrong format: {img.format}, expected PNG"
        assert img.mode == "RGB", f"Wrong mode: {img.mode}, expected RGB"
        
    print("✅ DeckManager image rendering output checked successfully.")

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
