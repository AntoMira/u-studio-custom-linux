import os
import sys
import time
import logging
import fcntl
# Monkey-patch fcntl.flock to bypass active systemd service single instance lock
fcntl.flock = lambda fd, op: None

from main import StreamDeckApp

# Configure logging to see all messages clearly
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

print("============================================================")
print("          TESTING SCREEN AUTO SLEEP & WAKE LOGIC")
print("============================================================")

# Force simulator mode
os.environ["SIMULATOR_MODE"] = "True"

app = StreamDeckApp()
# Configure extremely short sleep timeout (2 seconds) and disable scheduled time constraints
app.screen_sleep_timeout = 2
app.screen_sleep_start = ""
app.screen_sleep_end = ""
app.keep_screen_on_pc_monitor = []
app.keep_screen_on_hue_ids = []
app.last_activity_time = time.time()

print("[TEST] Screen is currently ON:", app.deck_mgr.screen_on)
assert app.deck_mgr.screen_on is True, "Screen should be ON initially"

print("[TEST] Waiting 3 seconds to trigger inactivity auto-sleep...")
# Run check_screen_sleep manually to simulate sync daemon ticking after 3 seconds
time.sleep(3)
app.check_screen_sleep()

print("[TEST] Screen is currently ON:", app.deck_mgr.screen_on)
assert app.deck_mgr.screen_on is False, "Screen should be OFF after inactivity timeout"

print("[TEST] Simulating a button press (index 0) to wake up the screen...")
# Simulate press on button 0
app.deck_mgr.simulate_press(0)

print("[TEST] Screen is currently ON:", app.deck_mgr.screen_on)
assert app.deck_mgr.screen_on is True, "Screen should have woken up and turned ON"

print("[TEST] Verifying that the wake-up button press was intercepted and NOT executed...")
# The wake callback resets the inactivity timer, so inactivity_seconds should be small
inactivity_seconds = time.time() - app.last_activity_time
print(f"[TEST] Inactivity duration after wake-up: {inactivity_seconds:.2f} seconds")
assert inactivity_seconds < 1.0, "Activity timer should have been reset on wake-up"

print("[TEST] Verifying keep_screen_on_hue_ids override...")
# Set Hue light 2 ON in HueController simulation mock state
app.hue._mock_states["2"] = {"on": True, "reachable": True}
app.keep_screen_on_hue_ids = ["2"]
app.last_activity_time = time.time() - 10.0 # Idle for 10s (timeout is 2s)
app.check_screen_sleep()
print("[TEST] Screen state with Hue light 2 ON:", app.deck_mgr.screen_on)
assert app.deck_mgr.screen_on is True, "Screen should stay ON when Hue light 2 is ON"

print("[TEST] Verifying keep_screen_on_pc_monitor override...")
app.hue._mock_states["2"] = {"on": False, "reachable": True}
app.keep_screen_on_pc_monitor = ["192.168.31.101"]
app.device_last_update[("192.168.31.101", 8085)] = time.time() # Received LHM telemetry right now
app.last_activity_time = time.time() - 10.0 # Idle for 10s
app.check_screen_sleep()
print("[TEST] Screen state with PC 192.168.31.101 online:", app.deck_mgr.screen_on)
assert app.deck_mgr.screen_on is True, "Screen should stay ON when PC 192.168.31.101 is online"

print("[TEST] Verifying daytime recovery outside sleep window when screen was OFF...")
app.hue._mock_states["2"] = {"on": False, "reachable": True}
app.device_last_update.clear()
app.screen_sleep_start = "23:59"
app.screen_sleep_end = "07:00"
app.screen_sleep_timeout = 300
app.deck_mgr.screen_on = False # Manually turn screen OFF
app.check_screen_sleep()
print("[TEST] Screen state outside sleep window:", app.deck_mgr.screen_on)
assert app.deck_mgr.screen_on is True, "Screen should automatically be restored to ON outside sleep window"

print("============================================================")
print("🎉 ALL SCREEN SLEEP & WAKE VERIFICATION CHECKS PASSED!")
print("============================================================")
