#!/usr/bin/env python3
"""
Linux Hardware Telemetry Exporter for Stream Deck (Ulanzi D200)
Exposes an HTTP server on port 8085 returning /data.json compatible with LibreHardwareMonitor format.

Usage:
    python3 linux_monitor_agent.py [--port 8085]
"""

import os
import sys
import json
import time
import socket
import argparse
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

def get_cpu_usage(prev_cpu_state=None):
    """Calculates CPU usage % from /proc/stat or fallback to loadavg."""
    try:
        with open("/proc/stat", "r") as f:
            fields = f.readline().split()[1:]
            vals = [float(x) for x in fields]
            idle = vals[3] + vals[4]
            total = sum(vals)
            if prev_cpu_state:
                prev_idle, prev_total = prev_cpu_state
                idle_delta = idle - prev_idle
                total_delta = total - prev_total
                if total_delta > 0:
                    usage = 100.0 * (1.0 - (idle_delta / total_delta))
                    return round(usage, 1), (idle, total)
            return 0.0, (idle, total)
    except Exception:
        try:
            load1, _, _ = os.getloadavg()
            cores = os.cpu_count() or 1
            return round(min(100.0, (load1 / cores) * 100.0), 1), None
        except Exception:
            return 0.0, None

def get_ram_usage():
    """Calculates physical RAM usage % from /proc/meminfo."""
    try:
        mem_data = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    mem_data[parts[0].strip()] = float(parts[1].strip().split()[0])
        total = mem_data.get("MemTotal", 1.0)
        free = mem_data.get("MemFree", 0.0)
        buffers = mem_data.get("Buffers", 0.0)
        cached = mem_data.get("Cached", 0.0)
        sreclaimable = mem_data.get("SReclaimable", 0.0)
        used = total - free - buffers - cached - sreclaimable
        return round(100.0 * (used / total), 1)
    except Exception:
        return 0.0

def get_cpu_temp():
    """Reads CPU temperature (°C) from /sys/class/thermal or /sys/class/hwmon."""
    try:
        thermal_paths = [
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/class/hwmon/hwmon0/temp1_input",
            "/sys/class/hwmon/hwmon1/temp1_input",
            "/sys/class/hwmon/hwmon2/temp1_input"
        ]
        for path in thermal_paths:
            if os.path.exists(path):
                with open(path, "r") as f:
                    val = float(f.read().strip())
                    if val > 1000:
                        val /= 1000.0
                    if 0 <= val <= 120:
                        return round(val, 1)
    except Exception:
        pass

    # Fallback to sensors command if available
    try:
        res = subprocess.run(["sensors"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if "Package id 0:" in line or "Tctl:" in line or "Core 0:" in line:
                    parts = line.split("+")
                    if len(parts) > 1:
                        temp_str = parts[1].split("°")[0].strip()
                        return round(float(temp_str), 1)
    except Exception:
        pass

    return 45.0

def get_gpu_stats():
    """Queries NVIDIA GPU stats via nvidia-smi if present."""
    usage, temp, vram = 0.0, None, 0.0
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,utilization.memory", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = res.stdout.strip().split("\n")[0].split(",")
            usage = float(parts[0].strip())
            temp = float(parts[1].strip())
            vram = float(parts[2].strip()) if len(parts) > 2 else 0.0
    except Exception:
        pass
    return usage, temp, vram

class TelemetryCollector:
    def __init__(self):
        self.hostname = socket.gethostname()
        self.prev_cpu = None
        # Prime CPU calculation
        _, self.prev_cpu = get_cpu_usage(None)
        time.sleep(0.1)

    def build_lhm_tree(self):
        cpu_pct, self.prev_cpu = get_cpu_usage(self.prev_cpu)
        ram_pct = get_ram_usage()
        cpu_temp = get_cpu_temp()
        gpu_pct, gpu_temp, gpu_vram = get_gpu_stats()

        cpu_children = [
            {
                "Text": "Load",
                "Children": [
                    {"Text": "CPU Total", "Value": f"{cpu_pct:.1f} %", "Children": []}
                ]
            },
            {
                "Text": "Temperatures",
                "Children": [
                    {"Text": "CPU Package", "Value": f"{cpu_temp:.1f} °C", "Children": []}
                ]
            }
        ]

        ram_children = [
            {
                "Text": "Load",
                "Children": [
                    {"Text": "Memory", "Value": f"{ram_pct:.1f} %", "Children": []}
                ]
            }
        ]

        server_children = [
            {"Text": "Generic CPU", "Children": cpu_children},
            {"Text": "Generic Memory", "Children": ram_children}
        ]

        if gpu_temp is not None:
            gpu_children = [
                {
                    "Text": "Load",
                    "Children": [
                        {"Text": "GPU Core", "Value": f"{gpu_pct:.1f} %", "Children": []},
                        {"Text": "GPU Memory", "Value": f"{gpu_vram:.1f} %", "Children": []}
                    ]
                },
                {
                    "Text": "Temperatures",
                    "Children": [
                        {"Text": "GPU Core", "Value": f"{gpu_temp:.1f} °C", "Children": []}
                    ]
                }
            ]
            server_children.append({"Text": "NVIDIA GPU", "Children": gpu_children})

        return {
            "Text": "SensorTree",
            "Children": [
                {
                    "Text": self.hostname,
                    "Children": server_children
                }
            ]
        }

collector = TelemetryCollector()

class MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default request logging to keep console clean
        pass

    def do_GET(self):
        if self.path in ("/data.json", "/data.json/"):
            tree = collector.build_lhm_tree()
            body = json.dumps(tree).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

def main():
    parser = argparse.ArgumentParser(description="Linux Hardware Telemetry Exporter for Stream Deck")
    parser.add_argument("--port", type=int, default=8085, help="HTTP Port to listen on (default: 8085)")
    parser.add_argument("--bind", default="0.0.0.0", help="Address to bind (default: 0.0.0.0)")
    args = parser.parse_args()

    server = HTTPServer((args.bind, args.port), MetricsHandler)
    print(f"============================================================")
    print(f"       LINUX HARDWARE TELEMETRY EXPORTER ACTIVE")
    print(f"============================================================")
    print(f"[INFO] Hostname : {collector.hostname}")
    print(f"[INFO] Listening: http://{args.bind}:{args.port}/data.json")
    print(f"[INFO] Ready to serve metrics to Stream Deck.")
    print(f"Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Exiting...")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
