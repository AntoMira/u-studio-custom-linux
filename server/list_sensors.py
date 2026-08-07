#!/usr/bin/env python3
import os
import sys
import yaml
import requests

def print_banner():
    print("=" * 70)
    print("      STREAM DECK - LIBREHARDWAREMONITOR SENSOR INSPECTOR")
    print("=" * 70)

def find_all_temperature_sensors(node, current_path=""):
    text = node.get("Text", "Unknown")
    new_path = f"{current_path} -> {text}" if current_path else text
    sensor_type = node.get("Type", "")
    val = node.get("Value")

    sensors = []
    # If this node represents a temperature sensor
    if sensor_type == "Temperature" or (val and "°C" in str(val)):
        sensors.append((new_path, text, str(val)))

    for child in node.get("Children", []):
        sensors.extend(find_all_temperature_sensors(child, new_path))

    return sensors

def inspect_sensors():
    print_banner()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.yaml")

    if not os.path.exists(config_path):
        print(f"❌ Error: Config file not found at {config_path}")
        sys.exit(1)

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    buttons = config.get("buttons", [])
    pc_buttons = [b for b in buttons if b.get("action_type") == "pc_monitor"]

    if not pc_buttons:
        print("⚠️ No pc_monitor buttons configured in config.yaml")
        return

    for btn in pc_buttons:
        btn_idx = btn.get("index")
        label = btn.get("label", "pc_monitor")
        ip = btn.get("ip", "localhost").strip()
        port = btn.get("port", 8085)
        mode = btn.get("mode", "pull")

        print(f"\n[Button Index {btn_idx}] Label: '{label}' | Mode: {mode} | IP: {ip} | Port: {port}")
        print("-" * 70)

        if ip.lower() in ("localhost", "127.0.0.1", "::1"):
            print("ℹ️ Local Host Server (Linux/Local metrics):")
            print("   - Sensor: CPU Package / Thermal Zone")
            print("   - Source: /sys/class/thermal or /proc/stat")
            continue

        if mode != "pull":
            print("   (Push mode is configured; sensors are received via UDP broadcast)")
            continue

        url = f"http://{ip}:{port}/data.json"
        try:
            print(f"Connecting to http://{ip}:{port}/data.json...")
            resp = requests.get(url, timeout=3.0)
            if resp.status_code == 200:
                tree = resp.json()
                temps = find_all_temperature_sensors(tree)

                if temps:
                    print(f"✅ Found {len(temps)} Temperature Sensor(s):\n")
                    for path, sensor_name, value in temps:
                        print(f"   • Sensor: '{sensor_name}' | Current Value: {value}")
                        print(f"     Full Path: {path}\n")
                else:
                    print("⚠️ Connected successfully, but no Temperature sensors were reported in data.json!")
            else:
                print(f"❌ HTTP Error {resp.status_code} returned by host {ip}:{port}")
        except Exception as e:
            print(f"❌ Connection failed to {url}: {e}")

    print("=" * 70)

if __name__ == "__main__":
    inspect_sensors()
