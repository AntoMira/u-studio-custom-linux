#!/usr/bin/env python3
import os
import sys
import argparse
import logging
from dotenv import load_dotenv
from hue_controller import HueController

# Configure basic console output logging
logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    # Load environment variables from .env
    load_dotenv()
    
    # Extract defaults from environment
    env_ip = os.getenv("HUE_BRIDGE_IP", "127.0.0.1")
    env_user = os.getenv("HUE_USERNAME", "mock_user")
    env_sim = os.getenv("SIMULATOR_MODE", "True").lower() in ("true", "1", "yes")

    # Command line argument parsing
    parser = argparse.ArgumentParser(
        description="Philips Hue Device and ID Listing Utility.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--ip", 
        default=env_ip, 
        help="Philips Hue Bridge IP Address"
    )
    parser.add_argument(
        "--user", 
        default=env_user, 
        help="Philips Hue Bridge Developer API Username"
    )
    
    # Mutual exclusivity for simulator / physical flags
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--simulator", "-s", 
        action="store_true", 
        default=env_sim,
        help="Force running in mock SIMULATOR MODE"
    )
    group.add_argument(
        "--physical", "-p", 
        action="store_false", 
        dest="simulator",
        help="Force running in PHYSICAL MODE against real bridge hardware"
    )

    args = parser.parse_args()

    print("\n=============================================================")
    print("           ESTABLISHING PHILIPS HUE CONNECTION")
    print("=============================================================")
    print(f"Bridge IP : {args.ip}")
    print(f"Username  : {args.user[:6]}..." if len(args.user) > 6 else f"Username  : {args.user}")
    print(f"Mode      : {'SIMULATOR (MOCK)' if args.simulator else 'PHYSICAL (HARDWARE)'}")
    print("=============================================================\n")

    # Instantiate Controller
    controller = HueController(
        bridge_ip=args.ip, 
        username=args.user, 
        simulator_mode=args.simulator
    )

    # Fetch all devices
    devices = controller.list_devices()

    if not devices:
        print("[-] Error: No devices returned. Verify your connection or credentials.")
        sys.exit(1)

    # Print out a beautifully formatted table of devices and IDs
    print("=============================================================================")
    print(f"{'DEVICE ID':<10} | {'DEVICE NAME':<25} | {'DEVICE TYPE':<25} | {'STATE':<8}")
    print("=============================================================================")
    
    # Sort device keys numerically if possible, otherwise alphabetically
    sorted_keys = sorted(devices.keys(), key=lambda x: int(x) if x.isdigit() else x)
    
    for dev_id in sorted_keys:
        info = devices[dev_id]
        
        # Handle difference between real bridge payload vs simulator mock payload structure
        name = info.get("name", f"Hue Device {dev_id}")
        dev_type = info.get("type", "Smart Device")
        
        # State detection
        is_on = False
        if "state" in info:
            is_on = info["state"].get("on", False)
        else:
            is_on = info.get("on", False)

        state_str = "ON" if is_on else "OFF"
        
        print(f"{dev_id:<10} | {name:<25} | {dev_type:<25} | {state_str:<8}")
        
    print("=============================================================================\n")

if __name__ == "__main__":
    main()
