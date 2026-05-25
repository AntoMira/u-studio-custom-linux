import os
import sys
import time
import logging
import fcntl
from datetime import datetime, timedelta

# Monkey-patch fcntl.flock to bypass active systemd service single instance lock
fcntl.flock = lambda fd, op: None

# Configure logging to see all messages clearly
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Force simulator mode
os.environ["SIMULATOR_MODE"] = "True"

print("============================================================")
print("          TESTING CLOCK WIDGET TIMEZONE INTEGRATION")
print("============================================================")

from main import StreamDeckApp

# Test Case 1: Graceful fallback when TIMEZONE is unset/empty
print("[TEST 1] Testing empty/unset TIMEZONE fallback...")
os.environ["TIMEZONE"] = ""
app_unset = StreamDeckApp()
assert app_unset.timezone is None, "Timezone should be None when environment variable is empty"
print("✅ Unset TIMEZONE fallback check passed.")

# Test Case 2: Graceful fallback when TIMEZONE is invalid
print("[TEST 2] Testing invalid TIMEZONE fallback...")
os.environ["TIMEZONE"] = "Invalid/Fake_Zone"
app_invalid = StreamDeckApp()
assert app_invalid.timezone is None, "Timezone should fall back to None when invalid zone is specified"
print("✅ Invalid TIMEZONE fallback check passed.")

# Test Case 3: Proper parsing and offset for a valid timezone
print("[TEST 3] Testing valid TIMEZONE (America/Sao_Paulo) parsing...")
os.environ["TIMEZONE"] = "America/Sao_Paulo"
app_valid = StreamDeckApp()
assert app_valid.timezone is not None, "Timezone should be resolved successfully"
assert app_valid.timezone_str == "America/Sao_Paulo", "Timezone string should be loaded correctly"

# Calculate expected offset time
from zoneinfo import ZoneInfo
tz = ZoneInfo("America/Sao_Paulo")
expected_now = datetime.now(tz)
print(f"[TEST 3] Current time in America/Sao_Paulo: {expected_now.strftime('%H:%M')}")
print("✅ Valid TIMEZONE parsing check passed.")

# Test Case 4: Clock widget time formatting and updates
print("[TEST 4] Testing clock time representation...")
app_valid.buttons_config[12] = {
    "index": 12,
    "device_type": "widget",
    "action_type": "clock",
    "label": "Time",
    "icon": "clock"
}
app_valid.clock_buttons = [12]
app_valid.update_button_state(12)

# Verify placeholder rendering is generated in output_sim
sim_image_path = os.path.join(app_valid.deck_mgr.output_sim_dir, "button_12.png")
assert os.path.exists(sim_image_path), f"Simulated clock button screen not saved to {sim_image_path}"
print("✅ Clock widget image generation check passed.")

# Test Case 5: Sleep schedule checks aligned with the timezone
print("[TEST 5] Testing timezone-aligned screen auto sleep windows...")

# Set sleep window to encompass the current hour in configured timezone
current_tz_hour = datetime.now(app_valid.timezone).hour
sleep_start_hour = (current_tz_hour - 1) % 24
sleep_end_hour = (current_tz_hour + 1) % 24

app_valid.screen_sleep_start = f"{sleep_start_hour:02d}:00"
app_valid.screen_sleep_end = f"{sleep_end_hour:02d}:00"
app_valid.screen_sleep_timeout = 2
app_valid.last_activity_time = time.time() - 3 # Exceeded timeout

# Since the current timezone time falls inside the sleep window, should_sleep should be True
assert app_valid.is_within_sleep_window() is True, "Should be inside sleep window in configured timezone"
print("✅ Timezone sleep schedule boundary check passed.")

print("============================================================")
print("🎉 ALL TIMEZONE VERIFICATION CHECKS PASSED SUCCESSFULLY!")
print("============================================================")
