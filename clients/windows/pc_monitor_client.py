#!/usr/bin/env python3
import os
import sys
import time
import json
import socket
import subprocess
import argparse

# Try importing psutil, print instructions if missing
try:
    import psutil
except ImportError:
    print("Error: 'psutil' library is required to run this script.")
    print("Please install it by running: pip install psutil")
    sys.exit(1)

def get_cpu_temp_wmi():
    """
    Attempts to read CPU temperature via WMI on Windows.
    Queries both OpenHardwareMonitor and LibreHardwareMonitor namespaces
    using PowerShell to avoid external python-wmi/pywin32 dependencies.
    """
    if sys.platform != "win32":
        return None

    # 1. Try standard ACPI Thermal Zone first via PowerShell
    try:
        cmd = 'Get-CimInstance -Namespace root\\wmi -ClassName MSAcpi_ThermalZoneTemperature | Select-Object -ExpandProperty CurrentTemperature'
        result = subprocess.run(["powershell", "-Command", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0 and result.stdout.strip():
            raw_temp = float(result.stdout.strip())
            return round((raw_temp / 10.0) - 273.15, 1)
    except Exception:
        pass

    # 2. Try LibreHardwareMonitor or OpenHardwareMonitor WMI namespace via PowerShell
    # Checks both namespaces: root\\LibreHardwareMonitor and root\\OpenHardwareMonitor
    namespaces = ["root\\LibreHardwareMonitor", "root\\OpenHardwareMonitor"]
    for ns in namespaces:
        try:
            # Query WMI Sensor for Temperature of CPU
            cmd = f'Get-CimInstance -Namespace "{ns}" -ClassName Sensor | Where-Object {{ $_.SensorType -eq "Temperature" -and ($_.Name -like "*CPU Core*" -or $_.Name -like "*CPU Package*") }} | Select-Object -ExpandProperty Value'
            result = subprocess.run(["powershell", "-Command", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                temps = [float(t.strip()) for t in lines if t.strip()]
                if temps:
                    # Return the average CPU core temperature
                    return round(sum(temps) / len(temps), 1)
        except Exception:
            pass

    return None

def get_gpu_stats():
    """
    Queries NVIDIA GPU utilization and temperature using the official nvidia-smi tool.
    Robust, fast, and does not require third-party python GPU dependencies.
    """
    usage = 0.0
    temp = None
    if sys.platform == "win32":
        # Standard Nvidia installation path in Windows
        nvsmi_path = os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "NVIDIA Corporation", "NVSMI", "nvidia-smi.exe")
        if not os.path.exists(nvsmi_path):
            nvsmi_path = "nvidia-smi" # Fallback to PATH
    else:
        nvsmi_path = "nvidia-smi"

    try:
        # Run query: utilization.gpu, temperature.gpu
        result = subprocess.run(
            [nvsmi_path, "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        output = result.stdout.strip()
        if output:
            parts = output.split(",")
            usage = float(parts[0].strip())
            temp = float(parts[1].strip())
    except Exception:
        # If nvidia-smi is not found or fails (no Nvidia GPU), return defaults
        pass

    return usage, temp

def main():
    parser = argparse.ArgumentParser(description="Windows hardware metrics transmitter for Stream Deck widget.")
    parser.add_argument("--host", default="255.255.255.255", help="Target UDP Broadcast or specific host IP (default: 255.255.255.255)")
    parser.add_argument("--port", type=int, default=9999, help="UDP port (default: 9999)")
    parser.add_argument("--interval", type=float, default=5.0, help="Sending interval in seconds (default: 5.0)")
    args = parser.parse_args()

    # Create UDP Socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    pc_name = socket.gethostname()
    print(f"============================================================")
    print(f"          WINDOWS HARDWARE TELEMETRY SENDER ACTIVE")
    print(f"============================================================")
    print(f"[INFO] Computer Name : {pc_name}")
    print(f"[INFO] Broadcasting to: {args.host}:{args.port}")
    print(f"[INFO] Interval      : {args.interval}s")
    print(f"------------------------------------------------------------")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            # 1. CPU Metrics
            cpu_usage = psutil.cpu_percent(interval=None) # Non-blocking read (uses diff since last check)
            cpu_temp = get_cpu_temp_wmi()

            # 2. Memory Metrics
            ram_usage = psutil.virtual_memory().percent

            # 3. Disk Metrics (checks primary partition)
            try:
                disk_path = "C:\\" if sys.platform == "win32" else "/"
                disk_usage = psutil.disk_usage(disk_path).percent
            except Exception:
                disk_usage = 0.0

            # 4. GPU Metrics (Nvidia)
            gpu_usage, gpu_temp = get_gpu_stats()

            # Build stats payload
            payload = {
                "pc_name": pc_name,
                "cpu_usage": cpu_usage,
                "cpu_temp": cpu_temp,
                "ram_usage": ram_usage,
                "gpu_usage": gpu_usage,
                "gpu_temp": gpu_temp,
                "disk_usage": disk_usage,
                "timestamp": int(time.time())
            }

            # Send via UDP Broadcast
            message = json.dumps(payload).encode("utf-8")
            sock.sendto(message, (args.host, args.port))

            # Console feedback
            temp_feedback = f" ({cpu_temp}°C)" if cpu_temp is not None else ""
            gpu_temp_feedback = f" ({gpu_temp}°C)" if gpu_temp is not None else ""
            print(f"[{time.strftime('%H:%M:%S')}] Sent -> CPU: {int(cpu_usage)}%{temp_feedback} | GPU: {int(gpu_usage)}%{gpu_temp_feedback} | RAM: {ram_usage}% | DISK: {disk_usage}%")
            
            # Wait for next interval
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[INFO] Stopping telemetry sender...")
    finally:
        sock.close()
        print("[INFO] Telemetry sender stopped safely.")

if __name__ == "__main__":
    main()
