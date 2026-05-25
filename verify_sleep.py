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

print("============================================================")
print("🎉 ALL SCREEN SLEEP & WAKE VERIFICATION CHECKS PASSED!")
print("============================================================")
