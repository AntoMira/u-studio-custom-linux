#!/usr/bin/env python3
import time
import json
import socket
import random
import argparse
import sys

def get_fluctuating_value(base, min_val, max_val):
    """Generates a value slightly deviated from base, bounded by min and max."""
    change = random.uniform(-5.0, 5.0)
    new_val = base + change
    return round(max(min(new_val, max_val), min_val), 1)

def main():
    parser = argparse.ArgumentParser(description="Simulate a Windows PC transmitting performance metrics over UDP broadcast.")
    parser.add_argument("--host", default="255.255.255.255", help="Target broadcast or IP address (default: 255.255.255.255)")
    parser.add_argument("--port", type=int, default=9999, help="UDP port (default: 9999)")
    parser.add_argument("--interval", type=float, default=5.0, help="Transmission interval in seconds (default: 5.0)")
    parser.add_argument("--name", default="DESKTOP-GAMING", help="Mock computer name (default: DESKTOP-GAMING)")
    args = parser.parse_args()

    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    print(f"Mock PC Client: Starting telemetry simulation for '{args.name}'...")
    print(f"Broadcasting to {args.host}:{args.port} every {args.interval}s")
    print("Press Ctrl+C to stop.")

    # Base values for realistic fluctuation
    base_cpu = 35.0
    base_cpu_temp = 55.0
    base_ram = 50.0
    base_gpu = 40.0
    base_gpu_temp = 60.0
    base_disk = 65.0

    try:
        while True:
            # Fluctuate mock data
            cpu_usage = get_fluctuating_value(base_cpu, 5.0, 100.0)
            cpu_temp = get_fluctuating_value(base_cpu_temp, 35.0, 95.0)
            ram_usage = get_fluctuating_value(base_ram, 10.0, 98.0)
            gpu_usage = get_fluctuating_value(base_gpu, 0.0, 100.0)
            gpu_temp = get_fluctuating_value(base_gpu_temp, 30.0, 90.0)
            disk_usage = get_fluctuating_value(base_disk, 10.0, 100.0)

            # Keep base moving slowly to simulate varying system loads over time
            base_cpu = get_fluctuating_value(base_cpu, 15.0, 75.0)
            base_gpu = get_fluctuating_value(base_gpu, 10.0, 80.0)

            payload = {
                "pc_name": args.name,
                "cpu_usage": cpu_usage,
                "cpu_temp": cpu_temp,
                "ram_usage": ram_usage,
                "gpu_usage": gpu_usage,
                "gpu_temp": gpu_temp,
                "disk_usage": disk_usage,
                "timestamp": int(time.time())
            }

            message = json.dumps(payload).encode("utf-8")
            sock.sendto(message, (args.host, args.port))
            
            print(f"Sent: CPU {cpu_usage}% ({cpu_temp}°C) | GPU {gpu_usage}% ({gpu_temp}°C) | RAM {ram_usage}% | DISK {disk_usage}%")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nMock PC Client stopped.")
    finally:
        sock.close()

if __name__ == "__main__":
    main()
