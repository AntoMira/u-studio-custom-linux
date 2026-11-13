import os
import logging
import time
import threading
import asyncio
from datetime import datetime
import math
from PIL import Image, ImageDraw, ImageFont, ImageOps
import unicodedata
from flight_service import compass_point as compass_point_pt

def strip_accents(text: str) -> str:
    """The bundled Pillow font has no accented glyphs: 'Aviões' -> 'Avioes'."""
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c))

# Set up logging format
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def get_color_for_temp(temp: float) -> tuple:
    """
    Computes an interpolated RGB color for a given temperature based on thresholds:
    <= 0: White (255, 255, 255)
    10: Cyan (0, 255, 255)
    24: Blue (0, 0, 255)
    30: Orange (255, 165, 0)
    >= 50: Red (255, 0, 0)
    """
    points = [
        (0.0, (255, 255, 255)),
        (10.0, (0, 255, 255)),
        (24.0, (0, 0, 255)),
        (30.0, (255, 165, 0)),
        (50.0, (255, 0, 0))
    ]
    if temp <= points[0][0]:
        return points[0][1]
    if temp >= points[-1][0]:
        return points[-1][1]
    for i in range(len(points) - 1):
        t1, c1 = points[i]
        t2, c2 = points[i+1]
        if t1 <= temp <= t2:
            factor = (temp - t1) / (t2 - t1)
            r = int(round(c1[0] + (c2[0] - c1[0]) * factor))
            g = int(round(c1[1] + (c2[1] - c1[1]) * factor))
            b = int(round(c1[2] + (c2[2] - c1[2]) * factor))
            return (r, g, b)
    return (0, 0, 0)

def get_scale_color(pct: float) -> tuple:
    """
    Smooth gradient color interpolation based on percentage (0% Green -> 50% Yellow -> 100% Red).
    """
    if pct is None:
        return (100, 100, 100) # Gray fallback
    p = min(100.0, max(0.0, float(pct))) / 100.0
    green_color = (46, 213, 115)   # #2ed573 Bright Green
    yellow_color = (255, 200, 0)   # #ffc800 Golden Yellow
    red_color = (255, 40, 40)      # #ff2828 Vibrant Red

    if p <= 0.5:
        factor = p / 0.5
        r = int(round(green_color[0] + (yellow_color[0] - green_color[0]) * factor))
        g = int(round(green_color[1] + (yellow_color[1] - green_color[1]) * factor))
        b = int(round(green_color[2] + (yellow_color[2] - green_color[2]) * factor))
    else:
        factor = (p - 0.5) / 0.5
        r = int(round(yellow_color[0] + (red_color[0] - yellow_color[0]) * factor))
        g = int(round(yellow_color[1] + (red_color[1] - yellow_color[1]) * factor))
        b = int(round(yellow_color[2] + (red_color[2] - yellow_color[2]) * factor))
    return (r, g, b)

class DeckManager:
    """
    Manages communication with the Ulanzi D200 Stream Deck.
    Features a robust Simulator Mode that saves button screens as PNG images for visual verification.
    """
    SMALL_WINDOW_INDEX = 13  # grid cell of the wide info screen (manifest cell 3_2)
    SMALL_WINDOW_SIZE = (458, 196)
    SMALL_WINDOW_BG_NAME = "small_window_bg.png"
    CACHE_GRACE_MS = 30000  # keep superseded button images this long so in-flight USB uploads can still read them

    def __init__(self, simulator_mode: bool = False, font_size_label: int = 30, font_size_status: int = 30, margin_label: int = 10, margin_status: int = 60, small_window_mode: int = 0, debounce_seconds: float = 0.35, reconnect_seconds: float = 10.0, small_window_background: str = ""):
        self.simulator_mode = simulator_mode
        self.has_hardware = not self.simulator_mode
        self.deck = None
        self.callbacks = []
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.output_sim_dir = os.path.join(base_dir, "output_sim")
        self.cache_dir = os.path.join(base_dir, ".cache", "icons", "_generated")
        self.font_size_label = font_size_label
        self.font_size_status = font_size_status
        self.margin_label = margin_label
        self.margin_status = margin_status
        self.small_window_mode = small_window_mode
        self.debounce_seconds = float(debounce_seconds)
        self.reconnect_seconds = max(1.0, float(reconnect_seconds))
        self.small_window_background = (small_window_background or "").strip()
        self.last_press_time = {}
        # Long press: {button_index: {"on": seconds, "off": seconds}} and in-flight press state
        self.long_press_config = {}
        self.long_press_callback = None
        self._press_state = {}
        self._press_lock = threading.Lock()
        os.makedirs(self.cache_dir, exist_ok=True)
        self.screen_on = True
        self.wake_callback = None

        if self.simulator_mode:
            logging.info("DeckManager: Initialized in SIMULATOR MODE. Generated images will be saved to output_sim/")
            # Create simulator output directory safely
            os.makedirs(self.output_sim_dir, exist_ok=True)
        else:
            logging.info("DeckManager: Initializing physical Ulanzi D200 Stream Deck connection...")
            self.active_buttons = {i: None for i in range(13)}
            self._init_small_window_background()
            self.first_update = True
            self._update_timer = None
            
            # Start background asyncio loop thread
            self.loop = asyncio.new_event_loop()
            self.loop_thread = threading.Thread(target=self._run_async_loop, daemon=True)
            self.loop_thread.start()

    async def _async_small_screen_reset(self):
        try:
            logging.info("DeckManager: Performing small screen reset sequence...")
            # 0. Hide default screen title/logo
            try:
                self.deck.set_label_style({'show_title': False}, force=True)
                logging.info("DeckManager: Set label style to show_title=False")
            except Exception as le:
                logging.error(f"DeckManager: Failed to set label style: {le}")

            # 1. Temporarily switch to BACKGROUND mode (2) to reset screen buffer
            self.deck.set_small_window_mode(2)
            self.deck.restore_small_window()
            await asyncio.sleep(0.3)
            
            # 2. Revert back to the configured user mode (e.g. CLOCK or STATS)
            self.deck.set_small_window_mode(self.small_window_mode)
            self.deck.restore_small_window()
            logging.info(f"DeckManager: Small screen reset completed. Applied mode: {self.small_window_mode}")
        except Exception as e:
            logging.error(f"DeckManager: Failed to set small window mode sequence: {e}")

    def _run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.create_task(self._hw_supervisor())
        self.loop.run_forever()

    def _init_small_window_background(self):
        """
        Replaces the D200 factory logo behind the clock/stats screen. The info screen shows the image
        uploaded for its grid cell with the page, so a solid black (or custom) image removes the logo.
        small_window_background: "" = solid black, "default" = keep the factory logo, otherwise an image path.
        """
        setting = self.small_window_background
        if setting.lower() == "default":
            return
        try:
            if setting:
                path = setting if os.path.isabs(setting) else os.path.join(os.path.dirname(os.path.abspath(__file__)), setting)
                with Image.open(path) as src:
                    img = ImageOps.fit(src.convert("RGB"), self.SMALL_WINDOW_SIZE)
            else:
                img = Image.new("RGB", self.SMALL_WINDOW_SIZE, (0, 0, 0))
            img.save(os.path.join(self.cache_dir, self.SMALL_WINDOW_BG_NAME))
            self.active_buttons[self.SMALL_WINDOW_INDEX] = {'name': '', 'icon': self.SMALL_WINDOW_BG_NAME}
        except Exception as e:
            logging.error(f"DeckManager: Failed to prepare small window background '{setting}': {e}")

    def _connect_hw(self):
        from strmdck.device_manager import auto_connect
        try:
            return auto_connect()
        except Exception as e:
            logging.error(f"DeckManager: Error while connecting to USB hardware: {e}")
            return None

    async def _hw_supervisor(self):
        """
        Keeps the D200 connected: connects, serves key events until the device is lost, then
        sleeps and retries. Sleeping between attempts keeps a missing device from burning CPU.
        """
        waiting_logged = False
        while True:
            deck = self._connect_hw()
            if not deck:
                if not waiting_logged:
                    logging.warning(f"DeckManager: Ulanzi D200 not found on USB. Retrying every {self.reconnect_seconds:.0f}s...")
                    waiting_logged = True
                await asyncio.sleep(self.reconnect_seconds)
                continue

            waiting_logged = False
            self.deck = deck
            logging.info("DeckManager: Physical Ulanzi D200 Stream Deck connected successfully!")
            keep_alive_task = None
            try:
                await self._async_small_screen_reset()
                self.deck.set_brightness(80 if self.screen_on else 0, True)
                if self.active_buttons and any(self.active_buttons.values()):
                    await self._async_set_buttons(dict(self.active_buttons))
                keep_alive_task = self.loop.create_task(self._hw_keep_alive_loop())
                await self._hw_read_loop()
            except Exception as e:
                logging.error(f"DeckManager: Hardware session error: {e}")
            finally:
                if keep_alive_task:
                    keep_alive_task.cancel()
                self._drop_hw()

            logging.warning(f"DeckManager: Lost connection to Ulanzi D200. Retrying in {self.reconnect_seconds:.0f}s...")
            await asyncio.sleep(self.reconnect_seconds)

    def _drop_hw(self):
        deck, self.deck = self.deck, None
        if deck:
            try:
                deck.close()
            except Exception as e:
                logging.debug(f"DeckManager: Error closing lost device: {e}")

    async def _hw_read_loop(self):
        """Returns when the device stops delivering packets (unplugged or read error)."""
        try:
            async for action in self.deck.read_packet():
                if action and hasattr(action, 'index'):
                    self._on_hardware_keypress(action.index, action.pressed)
        except Exception as e:
            logging.error(f"DeckManager: Error in hardware read loop: {e}")

    async def _hw_keep_alive_loop(self):
        while True:
            if not self.deck or not self.has_hardware:
                break
            try:
                # keep_alive() automatically updates the small information screen
                self.deck.keep_alive()
            except Exception as e:
                logging.error(f"DeckManager: Error in keep alive loop: {e}")
            await asyncio.sleep(1)

    def _hw_update_buttons(self):
        # Debounce the hardware update by 0.2 seconds to avoid USB flooding
        if self._update_timer:
            self._update_timer.cancel()
        
        self._update_timer = threading.Timer(0.2, self._push_to_hw)
        self._update_timer.start()

    def _push_to_hw(self):
        self._update_timer = None
        buttons_copy = dict(self.active_buttons)
        asyncio.run_coroutine_threadsafe(
            self._async_set_buttons(buttons_copy),
            self.loop
        )

    async def _async_set_buttons(self, buttons):
        try:
            # Force update_only=False to prevent D200 partial update bug that blanks other buttons
            update_only = False
            logging.info(f"DeckManager: Uploading page to D200 (update_only={update_only}, buttons={list(buttons.keys())})...")
            deck = self.deck
            if not deck:
                logging.warning("DeckManager: D200 not connected; button page will be sent on reconnect.")
                return
            deck.set_buttons(buttons, update_only=update_only)
            self.first_update = False
        except Exception as e:
            logging.error(f"DeckManager: Failed to set hardware buttons: {e}")

    def register_callback(self, callback):
        """
        Registers a callback function to handle button presses.
        Callback signature: func(button_index: int)
        """
        self.callbacks.append(callback)

    def register_wake_callback(self, callback):
        """
        Registers a callback function to handle screen wake events.
        """
        self.wake_callback = callback

    def set_screen_brightness(self, brightness: int):
        """
        Sets screen brightness thread-safely (brightness range 0-100).
        """
        logging.info(f"DeckManager: Setting screen brightness to {brightness}%")
        if self.simulator_mode:
            logging.info(f"DeckManager (SIM): Screen brightness updated to {brightness}%")
            return

        if self.deck and self.has_hardware:
            try:
                self.loop.call_soon_threadsafe(self.deck.set_brightness, brightness, True)
            except Exception as e:
                logging.error(f"DeckManager: Failed to write screen brightness to hardware: {e}")

    def _trigger_callbacks(self, button_index: int):
        """
        Triggers all registered button callbacks safely.
        """
        for callback in self.callbacks:
            try:
                callback(button_index)
            except Exception as e:
                logging.error(f"DeckManager: Error in button callback for index {button_index}: {e}")

    def register_long_press_callback(self, callback):
        """
        Registers callback(button_index, action) invoked when a hold threshold is reached.
        action is "on" or "off".
        """
        self.long_press_callback = callback

    def set_long_press_config(self, button_index: int, thresholds: dict):
        """
        Enables long press on a button. thresholds maps action ("on"/"off") to hold seconds.
        Buttons with long press fire their normal (short) callbacks on release instead of on press.
        """
        thresholds = {a: float(s) for a, s in thresholds.items() if a in ("on", "off") and s and float(s) > 0}
        if thresholds:
            self.long_press_config[button_index] = thresholds
        else:
            self.long_press_config.pop(button_index, None)

    def _fire_long_press(self, key_index: int, action: str, token: object):
        with self._press_lock:
            state = self._press_state.get(key_index)
            if not state or state["token"] is not token:
                return
            state["fired"] = True
        logging.info(f"DeckManager: Long press ({action}) on button {key_index}")
        if self.long_press_callback:
            try:
                self.long_press_callback(key_index, action)
            except Exception as e:
                logging.error(f"DeckManager: Error in long press callback for index {key_index}: {e}")

    def _cancel_press(self, key_index: int):
        """Drops in-flight press state and returns it (None if there was none)."""
        with self._press_lock:
            state = self._press_state.pop(key_index, None)
        if state:
            for timer in state["timers"]:
                timer.cancel()
        return state

    def _on_hardware_keypress(self, key_index: int, pressed: bool):
        """
        Internal handler for hardware button events.
        Triggers action on key press with debouncing. Buttons with long press configured
        trigger the short action on release (if no hold threshold was reached).
        """
        if not pressed:
            held = time.time() - self.last_press_time.get(key_index, 0.0)
            logging.info(f"DeckManager: Hardware Key Released: {key_index} (held {held:.2f}s)")
            state = self._cancel_press(key_index)
            if state and not state["fired"]:
                self._trigger_callbacks(key_index)
            return

        now = time.time()
        last_time = self.last_press_time.get(key_index, 0.0)
        elapsed = now - last_time
        if elapsed < self.debounce_seconds:
            logging.info(f"DeckManager: Debounced keypress on button {key_index} ({elapsed:.3f}s < {self.debounce_seconds}s)")
            return

        self.last_press_time[key_index] = now
        logging.info(f"DeckManager: Hardware Key Pressed: {key_index}")

        if not self.screen_on:
            self.screen_on = True
            self.set_screen_brightness(80)
            logging.info("DeckManager: Intercepted keypress to wake up the screen. Consumed press.")
            if self.wake_callback:
                try:
                    self.wake_callback()
                except Exception as e:
                    logging.error(f"DeckManager: Error in wake callback: {e}")
            return # Discard this keypress!

        thresholds = self.long_press_config.get(key_index)
        if not thresholds:
            self._trigger_callbacks(key_index)
            return

        self._cancel_press(key_index)
        token = object()
        timers = [threading.Timer(secs, self._fire_long_press, args=(key_index, action, token))
                  for action, secs in sorted(thresholds.items(), key=lambda kv: kv[1])]
        with self._press_lock:
            self._press_state[key_index] = {"token": token, "timers": timers, "fired": False}
        for timer in timers:
            timer.daemon = True
            timer.start()

    def simulate_press(self, button_index: int, force: bool = False) -> bool:
        """
        Triggered in Simulator Mode to emulate pressing a button.
        Returns True if the press was processed, False if debounced or consumed by wake-up.
        """
        if not force:
            now = time.time()
            last_time = self.last_press_time.get(button_index, 0.0)
            elapsed = now - last_time
            if elapsed < self.debounce_seconds:
                logging.info(f"DeckManager (SIM): Debounced keypress on button {button_index} ({elapsed:.3f}s < {self.debounce_seconds}s)")
                return False
            self.last_press_time[button_index] = now

        logging.info(f"DeckManager (SIM): Emulating button press for index: {button_index}")
        if not self.screen_on:
            self.screen_on = True
            self.set_screen_brightness(80)
            logging.info("DeckManager (SIM): Intercepted simulated keypress to wake up the screen. Consumed press.")
            if self.wake_callback:
                try:
                    self.wake_callback()
                except Exception as e:
                    logging.error(f"DeckManager: Error in wake callback: {e}")
            return False # Discard simulated press!

        self._trigger_callbacks(button_index)
        return True

    def reset_debounce(self, button_index: int = None):
        """
        Resets the debounce timer for a specific button or all buttons.
        """
        if button_index is None:
            self.last_press_time.clear()
        else:
            self.last_press_time.pop(button_index, None)

    @staticmethod
    def _draw_weather_icon(draw, center_x, center_y, weather_type, fg_color, accent=None):
        accent = accent or fg_color
        # Custom premium weather graphics
        if weather_type == "clear":
            # Draw a glowing sun
            sun_r = 18
            draw.ellipse([center_x - sun_r, center_y - sun_r, center_x + sun_r, center_y + sun_r], fill=None, outline=fg_color, width=3)
            # 8 radiating rays
            ray_len = 8
            for angle in range(0, 360, 45):
                rad = math.radians(angle)
                x1 = center_x + (sun_r + 4) * math.cos(rad)
                y1 = center_y + (sun_r + 4) * math.sin(rad)
                x2 = center_x + (sun_r + 4 + ray_len) * math.cos(rad)
                y2 = center_y + (sun_r + 4 + ray_len) * math.sin(rad)
                draw.line([x1, y1, x2, y2], fill=fg_color, width=2)
        elif weather_type == "clear_night":
            # Crescent moon: a disc with an offset disc carved out, drawn through a mask so it
            # works on both transparent icon canvases and solid button backgrounds
            moon_r = 20
            mask = Image.new("L", (2 * moon_r + 1, 2 * moon_r + 1), 0)
            mdraw = ImageDraw.Draw(mask)
            mdraw.ellipse([0, 0, 2 * moon_r, 2 * moon_r], fill=255)
            cut_x, cut_y, cut_r = moon_r + 11, moon_r - 8, 17
            mdraw.ellipse([cut_x - cut_r, cut_y - cut_r, cut_x + cut_r, cut_y + cut_r], fill=0)
            mx, my = center_x - 4, center_y + 2
            draw.bitmap((mx - moon_r, my - moon_r), mask, fill=fg_color)
            # Two small sparkling stars in the carved-out side
            for sx, sy, s in ((center_x + 17, center_y - 16, 5), (center_x + 22, center_y + 2, 3)):
                draw.line([sx - s, sy, sx + s, sy], fill=accent, width=2)
                draw.line([sx, sy - s, sx, sy + s], fill=accent, width=2)
        elif weather_type == "clouds":
            # Fluffy Cloud shape
            draw.ellipse([center_x - 22, center_y - 5, center_x - 5, center_y + 12], fill=fg_color)
            draw.ellipse([center_x - 13, center_y - 18, center_x + 13, center_y + 12], fill=fg_color)
            draw.ellipse([center_x + 5, center_y - 5, center_x + 22, center_y + 12], fill=fg_color)
            draw.rectangle([center_x - 18, center_y + 3, center_x + 18, center_y + 12], fill=fg_color)
        elif weather_type == "rain":
            # Cloud with raindrops
            draw.ellipse([center_x - 22, center_y - 10, center_x - 5, center_y + 7], fill=fg_color)
            draw.ellipse([center_x - 13, center_y - 23, center_x + 13, center_y + 7], fill=fg_color)
            draw.ellipse([center_x + 5, center_y - 10, center_x + 22, center_y + 7], fill=fg_color)
            draw.rectangle([center_x - 18, center_y - 2, center_x + 18, center_y + 7], fill=fg_color)
            # Raindrops
            draw.line([center_x - 10, center_y + 13, center_x - 13, center_y + 21], fill=accent, width=2)
            draw.line([center_x, center_y + 13, center_x - 3, center_y + 21], fill=accent, width=2)
            draw.line([center_x + 10, center_y + 13, center_x + 7, center_y + 21], fill=accent, width=2)
        elif weather_type == "thunderstorm":
            # Cloud with lightning bolt
            draw.ellipse([center_x - 22, center_y - 10, center_x - 5, center_y + 7], fill=fg_color)
            draw.ellipse([center_x - 13, center_y - 23, center_x + 13, center_y + 7], fill=fg_color)
            draw.ellipse([center_x + 5, center_y - 10, center_x + 22, center_y + 7], fill=fg_color)
            draw.rectangle([center_x - 18, center_y - 2, center_x + 18, center_y + 7], fill=fg_color)
            # Lightning zigzag
            draw.line([center_x + 3, center_y + 11, center_x - 3, center_y + 17], fill=accent, width=2)
            draw.line([center_x - 3, center_y + 17, center_x + 2, center_y + 17], fill=accent, width=2)
            draw.line([center_x + 2, center_y + 17, center_x - 3, center_y + 24], fill=accent, width=2)
        elif weather_type == "snow":
            # Cloud with snow crosses
            draw.ellipse([center_x - 22, center_y - 10, center_x - 5, center_y + 7], fill=fg_color)
            draw.ellipse([center_x - 13, center_y - 23, center_x + 13, center_y + 7], fill=fg_color)
            draw.ellipse([center_x + 5, center_y - 10, center_x + 22, center_y + 7], fill=fg_color)
            draw.rectangle([center_x - 18, center_y - 2, center_x + 18, center_y + 7], fill=fg_color)
            # Snowflake crosses
            draw.line([center_x - 10, center_y + 15, center_x - 6, center_y + 15], fill=accent, width=2)
            draw.line([center_x - 8, center_y + 13, center_x - 8, center_y + 17], fill=accent, width=2)
            draw.line([center_x + 8, center_y + 15, center_x + 4, center_y + 15], fill=accent, width=2)
            draw.line([center_x + 6, center_y + 13, center_x + 6, center_y + 17], fill=accent, width=2)
        elif weather_type == "mist":
            # Horizontal fog/breeze lines
            draw.rectangle([center_x - 22, center_y - 9, center_x + 22, center_y - 6], fill=fg_color)
            draw.rectangle([center_x - 13, center_y - 2, center_x + 18, center_y + 1], fill=fg_color)
            draw.rectangle([center_x - 18, center_y + 5, center_x + 13, center_y + 8], fill=fg_color)

    WEEKDAYS_PT = ("SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM")
    # weather type -> (main color, accent for drops / bolt / flakes)
    WEATHER_ICON_COLORS = {
        "clear": ((255, 205, 50), None),
        "clear_night": ((235, 225, 175), (255, 240, 190)),
        "clouds": ((245, 245, 250), None),
        "rain": ((150, 165, 190), (80, 170, 255)),
        "thunderstorm": ((125, 130, 155), (255, 215, 60)),
        "snow": ((170, 185, 205), (255, 255, 255)),
        "mist": ((175, 180, 190), None),
    }

    @staticmethod
    def _soft_temp_color(temp: float) -> tuple:
        """Temperature gradient color lightened so it stays readable on a black background."""
        r, g, b = get_color_for_temp(temp)
        return (int(r + (255 - r) * 0.4), int(g + (255 - g) * 0.4), int(b + (255 - b) * 0.4))

    def _paste_weather_icon(self, img, cx, cy, weather_type, scale=1.0):
        icon = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        color, accent = self.WEATHER_ICON_COLORS.get(weather_type, ((255, 255, 255), None))
        self._draw_weather_icon(ImageDraw.Draw(icon), 32, 32, weather_type, color, accent)
        size = int(64 * scale)
        if size > 64:
            # Upscale in blocks then downsample, which antialiases the 1px geometric edges
            icon = icon.resize((256, 256), Image.NEAREST).resize((size, size), Image.LANCZOS)
        elif size != 64:
            icon = icon.resize((size, size), Image.LANCZOS)
        img.paste(icon, (int(cx - size / 2), int(cy - size / 2)), icon)

    @staticmethod
    def _draw_drop(draw, x, y, color, h=14):
        """Small raindrop with its tip at (x, y)."""
        w = h * 0.36
        draw.polygon([(x, y), (x - w, y + h * 0.6), (x + w, y + h * 0.6)], fill=color)
        draw.ellipse([x - w, y + h * 0.3, x + w, y + h], fill=color)

    def _draw_rain_chance(self, draw, x, y, pop, right_aligned=False):
        pct = int(round(pop * 100))
        if pct < 30:
            return
        font = ImageFont.load_default(size=16)
        label = f"{pct}%"
        tw = draw.textlength(label, font=font)
        total = 10 + 4 + tw
        x0 = x - total if right_aligned else x - total / 2
        self._draw_drop(draw, x0 + 5, y, (110, 175, 255), h=14)
        draw.text((x0 + 14, y + 7), label, font=font, fill=(150, 200, 255), anchor="lm")

    def _draw_weather_current(self, img, draw, current: dict, today: dict, left_w: int = 148) -> int:
        """Draws the left 'AGORA' block shared by the weather panels and returns its width."""
        height = self.SMALL_WINDOW_SIZE[1]
        f = lambda size: ImageFont.load_default(size=size)
        white = (255, 255, 255)
        draw.text((10, 8), "AGORA", font=f(22), fill=white, anchor="lt")
        self._paste_weather_icon(img, left_w // 2, 58, current.get("type", "clear"), scale=1.3)
        cur_temp = current.get('temp', 0)
        draw.text((left_w // 2, 96), f"{int(round(cur_temp))}°", font=f(54), fill=self._soft_temp_color(cur_temp), anchor="mt")
        if today:
            lo_t, hi_t = today['min_temp'], today['max_temp']
            lo_s, hi_s = f"{int(round(lo_t))}°", f"{int(round(hi_t))}°"
            sep = " / "
            fr = f(26)
            total = draw.textlength(lo_s, font=fr) + draw.textlength(sep, font=fr) + draw.textlength(hi_s, font=fr)
            x = left_w / 2 - total / 2
            for txt, col in ((lo_s, self._soft_temp_color(lo_t)), (sep, white), (hi_s, self._soft_temp_color(hi_t))):
                draw.text((x, 150), txt, font=fr, fill=col, anchor="lt")
                x += draw.textlength(txt, font=fr)
        if current.get("pop", 0) >= 0.3:
            self._draw_rain_chance(draw, left_w - 8, 8, current["pop"], right_aligned=True)
        draw.line([left_w, 14, left_w, height - 23], fill=(55, 55, 62), width=2)
        return left_w

    def render_weather_panel(self, current: dict, today: dict, days: list):
        """
        Renders the 458x196 weather panel: current conditions + today's range on the left,
        followed by one column per upcoming day (weekday, icon, max/min with a range bar, rain chance).
        current: {temp, pop, type}; today: {min_temp, max_temp}; days: [{date(ISO), min_temp, max_temp, type, pop}]
        """
        width, height = self.SMALL_WINDOW_SIZE
        img = Image.new("RGB", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        f = lambda size: ImageFont.load_default(size=size)
        white = (255, 255, 255)

        left_w = self._draw_weather_current(img, draw, current, today)

        # --- Day columns ---
        days = days[:4]
        if not days:
            return img
        col_x0 = left_w + 6
        col_w = (width - col_x0 - 4) / len(days)
        for i, day in enumerate(days):
            cx = col_x0 + col_w * (i + 0.5)
            try:
                wd = self.WEEKDAYS_PT[datetime.fromisoformat(day["date"]).weekday()]
            except Exception:
                wd = "---"
            draw.text((cx, 8), wd, font=f(24), fill=white, anchor="mt")
            self._paste_weather_icon(img, cx, 56, day.get("type", "clear"), scale=1.0)
            draw.text((cx, 82), f"{int(round(day['max_temp']))}°", font=f(32), fill=self._soft_temp_color(day["max_temp"]), anchor="mt")
            draw.text((cx, 118), f"{int(round(day['min_temp']))}°", font=f(32), fill=self._soft_temp_color(day["min_temp"]), anchor="mt")
            self._draw_rain_chance(draw, cx, 158, day.get("pop", 0))
        return img

    def update_weather_panel(self, current: dict, today: dict, days: list):
        """
        Renders the weather panel and shows it on the wide info screen (small window cell).
        """
        img = self.render_weather_panel(current, today, days)
        if self.simulator_mode:
            try:
                img.save(os.path.join(self.output_sim_dir, "weather_panel.png"))
            except Exception as e:
                logging.error(f"DeckManager (SIM): Failed to save weather panel: {e}")
            return
        self._store_hw_image(self.SMALL_WINDOW_INDEX, img)

    WEATHER_GRAPH_MAX_RAIN_MM = 30.0  # rain per 3 h that fills the graph height (very heavy rain)

    def render_weather_graph(self, current: dict, today: dict, hourly: list):
        """
        Renders the 458x196 weather graph: the same current-conditions block as the weather panel,
        followed by one bar per 3-hour forecast (height = temperature on a 0-45 scale, color = temperature
        scale). A dotted gray line marks each midnight.
        hourly: [{date(ISO), temp, rain(mm per 3 h)}] in chronological order.
        A translucent blue curve over the bars shows the rain, 0 to WEATHER_GRAPH_MAX_RAIN_MM.
        """
        width, height = self.SMALL_WINDOW_SIZE
        img = Image.new("RGB", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        left_w = self._draw_weather_current(img, draw, current, today)
        if not hourly:
            return img

        x0, x1 = left_w + 12, width - 8
        top, bottom = 30, height - 25
        t_min, t_max = 0.0, 45.0
        slot = (x1 - x0) / len(hourly)
        bar_w = max(2, int(slot) - 2)
        for i, item in enumerate(hourly):
            sx = x0 + slot * i
            temp = item["temp"]
            frac = min(max((temp - t_min) / (t_max - t_min), 0.0), 1.0)
            bar_h = max(2, int(round((bottom - top) * frac)))
            bx = int(sx + (slot - bar_w) / 2)
            draw.rectangle([bx, bottom - bar_h, bx + bar_w - 1, bottom], fill=self._soft_temp_color(temp))
            if i > 0 and item["date"] != hourly[i - 1]["date"]:
                lx = int(round(sx))
                for y in range(top - 6, bottom, 6):
                    draw.line([lx, y, lx, y + 2], fill=(255, 255, 255), width=2)

        self._draw_rain_curve(img, hourly, x0, slot, top, bottom)
        draw = ImageDraw.Draw(img)

        # Weekday label centered over each day's run of bars (skipped when the run is too narrow)
        label_font = ImageFont.load_default(size=16)
        start = 0
        for i in range(1, len(hourly) + 1):
            if i == len(hourly) or hourly[i]["date"] != hourly[start]["date"]:
                try:
                    wd = self.WEEKDAYS_PT[datetime.fromisoformat(hourly[start]["date"]).weekday()]
                except Exception:
                    wd = ""
                seg_x0, seg_x1 = x0 + slot * start, x0 + slot * i
                if wd and draw.textlength(wd, font=label_font) + 4 <= seg_x1 - seg_x0:
                    draw.text(((seg_x0 + seg_x1) / 2, 4), wd, font=label_font, fill=(255, 255, 255), anchor="mt")
                start = i
        return img

    def _draw_rain_curve(self, img, hourly: list, x0: float, slot: float, top: int, bottom: int):
        """Draws the rain as a smooth translucent white area (with a solid edge only where it rains) over the bars."""
        if not any(h.get("rain", 0) > 0 for h in hourly):
            return
        rain_h = bottom - top
        pts = [
            (x0 + slot * (i + 0.5), bottom - rain_h * min(max(h.get("rain", 0.0) / self.WEATHER_GRAPH_MAX_RAIN_MM, 0.0), 1.0))
            for i, h in enumerate(hourly)
        ]
        # Catmull-Rom spline through the points; y is clamped so the curve never dips below 0 mm
        curve = []
        steps = 8
        for i in range(len(pts) - 1):
            p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, len(pts) - 1)]
            for k in range(steps):
                t = k / steps
                t2, t3 = t * t, t * t * t
                x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
                y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
                curve.append((x, min(max(y, top), bottom)))
        curve.append(pts[-1])
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.polygon(curve + [(curve[-1][0], bottom), (curve[0][0], bottom)], fill=(255, 255, 255, 120))
        # Edge only where there is rain: skip the segments lying on the 0 mm baseline
        for a, b in zip(curve, curve[1:]):
            if a[1] < bottom - 0.5 or b[1] < bottom - 0.5:
                odraw.line([a, b], fill=(255, 255, 255, 255), width=2)
        img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))

    def update_weather_graph(self, current: dict, today: dict, hourly: list):
        img = self.render_weather_graph(current, today, hourly)
        if self.simulator_mode:
            try:
                img.save(os.path.join(self.output_sim_dir, "weather_graph.png"))
            except Exception as e:
                logging.error(f"DeckManager (SIM): Failed to save weather graph: {e}")
            return
        self._store_hw_image(self.SMALL_WINDOW_INDEX, img)

    # ------------------------------------------------------------------ flight radar
    # airline short name -> accent color of the top bar
    FLIGHT_AIRLINE_COLORS = {
        "LATAM": (232, 17, 91), "LATAM CARGO": (232, 17, 91), "GOL": (255, 112, 32),
        "AZUL": (0, 110, 215), "AZUL CONECTA": (0, 110, 215), "PASSAREDO": (230, 160, 0),
        "VOEPASS": (230, 160, 0), "FAB": (60, 140, 60),
    }
    FLIGHT_SKY = (8, 22, 44)

    @staticmethod
    def _flight_icon(is_heli: bool, size: int, color=(255, 255, 255)):
        """Top view of an airplane (or helicopter) pointing up, on a transparent square."""
        s = 256
        icon = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(icon)
        c = s // 2
        if is_heli:
            d.ellipse([c - 34, c - 62, c + 34, c + 30], fill=color)                    # cabin
            d.rectangle([c - 9, c + 20, c + 9, c + 112], fill=color)                    # tail boom
            d.rectangle([c - 34, c + 96, c + 34, c + 110], fill=color)                  # tail stabilizer
            for ang in (45, 135):                                                        # main rotor
                a = math.radians(ang)
                dx, dy = math.cos(a) * 118, math.sin(a) * 118
                d.line([c - dx, c - 16 - dy, c + dx, c - 16 + dy], fill=color, width=14)
            d.ellipse([c - 16, c - 32, c + 16, c], fill=color)
        else:
            d.rounded_rectangle([c - 17, c - 118, c + 17, c + 104], radius=17, fill=color)  # fuselage
            d.polygon([(c - 12, c - 30), (c - 124, c + 24), (c - 124, c + 44), (c - 12, c + 18),
                       (c + 12, c + 18), (c + 124, c + 44), (c + 124, c + 24), (c + 12, c - 30)], fill=color)  # wings
            d.polygon([(c - 10, c + 70), (c - 52, c + 100), (c - 52, c + 114), (c - 10, c + 98),
                       (c + 10, c + 98), (c + 52, c + 114), (c + 52, c + 100), (c + 10, c + 70)], fill=color)  # tail
        return icon.resize((size, size), Image.LANCZOS)

    def _paste_rotated_icon(self, img, cx, cy, is_heli, size, angle, color=(255, 255, 255)):
        icon = self._flight_icon(is_heli, size, color)
        if angle:
            icon = icon.rotate(-angle, resample=Image.BICUBIC)  # PIL rotates counter-clockwise
        img.paste(icon, (int(cx - size / 2), int(cy - size / 2)), icon)

    @staticmethod
    def _fit_font(draw, text, max_w, size, min_size=14):
        while size > min_size:
            font = ImageFont.load_default(size=size)
            if draw.textlength(strip_accents(text), font=font) <= max_w:
                return font
            size -= 2
        return ImageFont.load_default(size=min_size)

    @staticmethod
    def _draw_centered(draw, y, text, font, fill=(255, 255, 255), cx=98):
        text = strip_accents(text)
        draw.text((cx - draw.textlength(text, font=font) / 2, y), text, fill=fill, font=font)

    @staticmethod
    def _draw_vertical_arrow(draw, x, y, up: bool, color, h=12):
        if up:
            draw.polygon([(x, y), (x - h * 0.6, y + h), (x + h * 0.6, y + h)], fill=color)
        else:
            draw.polygon([(x, y + h), (x - h * 0.6, y), (x + h * 0.6, y)], fill=color)

    @staticmethod
    def _fmt_km(km: float) -> str:
        return f"{km:.1f}".replace(".", ",") + " km" if km < 10 else f"{km:.0f} km"

    def _draw_flight_dots(self, draw, idx, total, y=184):
        if total <= 1:
            return
        shown = min(total, 7)
        gap = 12
        x0 = 98 - (shown - 1) * gap / 2
        for i in range(shown):
            r = 3.5 if i == idx % shown else 2.5
            fill = (255, 255, 255) if i == idx % shown else (110, 120, 140)
            draw.ellipse([x0 + i * gap - r, y - r, x0 + i * gap + r, y + r], fill=fill)

    FLIGHT_PROJECTION_SECONDS = 120  # length of the dashed "where it is going" line

    @staticmethod
    def _draw_clipped_line(draw, p0, p1, center, radius, fill, width=2, dash=None):
        """Draws p0->p1 only where it lies inside the circle, optionally dashed (on_px, off_px)."""
        (x0, y0), (x1, y1) = p0, p1
        length = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(length / 1.5))
        run = []
        period = sum(dash) if dash else 0

        def flush():
            if len(run) >= 2:
                draw.line(run, fill=fill, width=width)
            run.clear()

        for i in range(steps + 1):
            t = i / steps
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            inside = math.hypot(x - center[0], y - center[1]) <= radius
            on = not dash or (t * length) % period < dash[0]
            if inside and on:
                run.append((x, y))
            else:
                flush()
        flush()

    def render_flight_button(self, flight: dict, page: int, idx: int = 0, total: int = 1,
                             facing: float = 0.0, max_distance_km: float = 5.0):
        """
        Renders one 196x196 flight screen.
        page 0: who it is (airline/flight number or registration, aircraft type, route)
        page 1: where it is (mini radar oriented to the direction the deck faces, distance, altitude, speed)
        """
        w = h = 196
        emergency = flight.get("emergency")
        img = Image.new("RGB", (w, h), (90, 0, 0) if emergency else self.FLIGHT_SKY)
        draw = ImageDraw.Draw(img)
        white, grey = (255, 255, 255), (170, 182, 200)
        is_heli = flight.get("is_heli")

        airline = flight.get("airline") or (flight.get("airline_code") if flight.get("is_airline") else None)
        title = airline or ("HELICOPTERO" if is_heli else "AERONAVE")
        accent = self.FLIGHT_AIRLINE_COLORS.get(airline or "", (70, 90, 120))
        main = flight.get("flight_number") or flight.get("registration") or flight.get("callsign") or flight.get("hex", "").upper()

        if page == 0:
            if emergency:
                title, accent = f"EMERG. {flight.get('squawk', '')}".strip(), (220, 30, 30)
            draw.rectangle([0, 0, w, 40], fill=accent)
            self._draw_centered(draw, 8, title, self._fit_font(draw, title, 184, 26), white)

            self._draw_centered(draw, 50, main, self._fit_font(draw, main, 184, 46), white)

            type_code = flight.get("type") or "?"
            font_t = ImageFont.load_default(size=22)
            tw = draw.textlength(type_code, font=font_t)
            x0 = 98 - (tw + 30) / 2
            self._paste_rotated_icon(img, x0 + 11, 117, is_heli, 24, 45 if not is_heli else 0, grey)
            draw.text((x0 + 30, 105), type_code, fill=grey, font=font_t)

            route = flight.get("route") or {}
            if route.get("origin") and route.get("destination"):
                font_r = ImageFont.load_default(size=28)
                o, d_ = route["origin"], route["destination"]
                ow, dw = draw.textlength(o, font=font_r), draw.textlength(d_, font=font_r)
                gap = 34
                x = 98 - (ow + gap + dw) / 2
                draw.text((x, 138), o, fill=white, font=font_r)
                ax = x + ow + 6
                draw.line([ax, 153, ax + gap - 14, 153], fill=white, width=3)
                draw.polygon([(ax + gap - 12, 153), (ax + gap - 20, 147), (ax + gap - 20, 159)], fill=white)
                draw.text((x + ow + gap, 138), d_, fill=white, font=font_r)
            else:
                sub = flight.get("registration") if flight.get("flight_number") else flight.get("callsign")
                if sub and sub.replace("-", "") != main.replace("-", ""):
                    self._draw_centered(draw, 140, sub, ImageFont.load_default(size=24), white)
        else:
            # slim bar with the same airline color + who it is, linking this screen to the first one
            tag = f"{airline} {main}" if airline else ("HELI " if is_heli else "") + main
            if emergency:
                accent = (220, 30, 30)
            draw.rectangle([0, 0, w, 24], fill=accent)
            self._draw_centered(draw, 3, tag, self._fit_font(draw, tag, 184, 18, min_size=12), white)

            dist = flight.get("distance_km", 0.0)
            bearing = flight.get("bearing", 0.0)
            top = f"{self._fmt_km(dist)}  {compass_point_pt(bearing)}"
            self._draw_centered(draw, 28, top, self._fit_font(draw, top, 184, 22), white)

            # mini radar: center = you, up = direction the deck faces
            cx, cy, r = 98, 97, 40
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(60, 80, 110), width=2)
            draw.ellipse([cx - r / 2, cy - r / 2, cx + r / 2, cy + r / 2], outline=(40, 56, 80), width=1)
            draw.polygon([(cx, cy - r - 2), (cx - 6, cy - r + 8), (cx + 6, cy - r + 8)], fill=(110, 130, 160))  # "ahead" tick
            # north marker on the ring
            na = math.radians(-facing)
            nx, ny = cx + math.sin(na) * r, cy - math.cos(na) * r
            font_n = ImageFont.load_default(size=13)
            draw.ellipse([nx - 8, ny - 8, nx + 8, ny + 8], fill=self.FLIGHT_SKY if not emergency else (90, 0, 0), outline=(110, 130, 160))
            draw.text((nx - draw.textlength("N", font=font_n) / 2, ny - 8), "N", fill=(200, 210, 230), font=font_n)
            draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(80, 200, 120))  # you
            scale = (r - 4) / (max_distance_km or 1.0)  # px per km

            def to_px(d_km, brg):
                a = math.radians(brg - facing)
                return cx + math.sin(a) * d_km * scale, cy - math.cos(a) * d_km * scale

            px, py = to_px(dist, bearing)
            bg = (90, 0, 0) if emergency else self.FLIGHT_SKY
            trail_color = (255, 215, 64)
            # where it has been: solid line fading out towards the oldest point
            pts = [to_px(d_, b_) for d_, b_ in (flight.get("trail") or [])] + [(px, py)]
            n = len(pts) - 1
            for i in range(n):
                k = 0.3 + 0.6 * (i + 1) / n
                col = tuple(int(bg[c] + (trail_color[c] - bg[c]) * k) for c in range(3))
                self._draw_clipped_line(draw, pts[i], pts[i + 1], (cx, cy), r - 1, col, 3)
            # where it is going: dashed line, PROJECTION_SECONDS ahead at the current track and speed
            track = flight.get("track")
            spd = flight.get("speed_kmh")
            if track is not None and spd:
                ahead_km = spd * self.FLIGHT_PROJECTION_SECONDS / 3600.0
                a = math.radians(track - facing)
                ux, uy = math.sin(a), -math.cos(a)
                start = (px + ux * 12, py + uy * 12)  # begin past the nose of the icon
                end = (px + ux * (12 + ahead_km * scale), py + uy * (12 + ahead_km * scale))
                self._draw_clipped_line(draw, start, end, (cx, cy), r - 1, (230, 235, 245), 2, dash=(4, 4))
            heading = ((track if track is not None else bearing) - facing) % 360
            self._paste_rotated_icon(img, px, py, is_heli, 24, heading if not is_heli else 0, (255, 215, 64))

            # altitude (with climb/descent arrow) and speed
            font_b = ImageFont.load_default(size=22)
            alt = flight.get("altitude_m")
            alt_txt = "SOLO" if flight.get("on_ground") else (f"{int(round(alt / 10.0) * 10):,} m".replace(",", ".") if alt is not None else "-- m")
            spd = flight.get("speed_kmh")
            spd_txt = f"{int(round(spd))} km/h" if spd is not None else ""
            vr = flight.get("vertical_rate") or 0
            arrow = abs(vr) >= 300
            aw = draw.textlength(alt_txt, font=font_b) + (16 if arrow else 0)
            x = 98 - aw / 2
            draw.text((x, 143), alt_txt, fill=white, font=font_b)
            if arrow:
                self._draw_vertical_arrow(draw, x + aw - 6, 149, vr > 0, (80, 200, 120) if vr > 0 else (255, 160, 60))
            if spd_txt:
                self._draw_centered(draw, 168, spd_txt, ImageFont.load_default(size=15), grey)

        self._draw_flight_dots(draw, idx, total, y=190 if page == 1 else 184)
        return img

    def render_flight_idle(self, label: str = "Radar", status: str = "SEM VOOS"):
        """Idle screen: a big airplane drawing when nothing is inside the radius."""
        w = h = 196
        img = Image.new("RGB", (w, h), self.FLIGHT_SKY)
        draw = ImageDraw.Draw(img)
        self._paste_rotated_icon(img, 98, 92, False, 92, 45, (235, 240, 250))
        font_l = ImageFont.load_default(size=self.font_size_label)
        self._draw_centered(draw, self.margin_label, label, font_l)
        font_s = self._fit_font(draw, status, 184, min(self.font_size_status, 24))
        self._draw_centered(draw, h - 40, status, font_s, (170, 182, 200))
        return img

    def show_button_image(self, index: int, img, sim_name: str = None):
        """Shows an already rendered 196x196 image on a key (or saves it in Simulator Mode)."""
        if self.simulator_mode:
            try:
                img.save(os.path.join(self.output_sim_dir, sim_name or f"button_{index}.png"))
            except Exception as e:
                logging.error(f"DeckManager (SIM): Failed to save button {index} image: {e}")
            return
        self._store_hw_image(index, img)

    def update_button(self, index: int, label: str, device_type: str, is_on: bool, brightness: int = None, icon_path: str = None, text_override: str = None, font_size_label: int = None, font_size_status: int = None, margin_label: int = None, margin_status: int = None, reachable: bool = True, weather_type: str = None, min_temp: float = None, max_temp: float = None, cpu_pct: float = None, mem_pct: float = None, temp_val: float = None, col_labels: tuple = None, center_text: str = None, power_val: float = None, max_power: float = 1000.0):
        """
        Draws the button image using Pillow and pushes it to the D200 key (or saves it in Simulator Mode).
        * index: Button index (0 to 12)
        * label: Label text displayed at the top of the button
        * device_type: 'light', 'plug', or 'widget'
        * is_on: True/False state
        * brightness: Brightness percentage (0-100) for dimmable lights
        * icon_path: Optional path to a base icon PNG
        * text_override: For widgets like clocks to display time directly (e.g., "15:20")
        * reachable: True if the device is connected and responding, False otherwise
        * weather_type: 'clear', 'clouds', 'rain', 'thunderstorm', 'snow', or 'mist'
        * min_temp: Forecastead minimum temperature for gradient calculations
        * max_temp: Forecastead maximum temperature for gradient calculations
        """
        # Validate button index
        if index < 0 or index > 12:
            logging.error(f"DeckManager: Button index out of bounds: {index}")
            return

        # Resolve font sizes with defaults
        if font_size_label is None:
            font_size_label = self.font_size_label
        if font_size_status is None:
            font_size_status = self.font_size_status

        # Resolve margins with defaults
        if margin_label is None:
            margin_label = self.margin_label
        if margin_status is None:
            margin_status = self.margin_status

        # 1. Determine Background Color or Gradient based on State, Reachability, and Device Type
        is_gradient = False
        is_weather_solid = False
        if device_type == "widget" and min_temp is not None and max_temp is not None:
            is_gradient = True
            min_color = get_color_for_temp(min_temp)
            max_color = get_color_for_temp(max_temp)
        elif device_type == "widget" and min_temp is not None:
            is_weather_solid = True
            bg_color = get_color_for_temp(min_temp)
        elif not reachable:
            bg_color = (0, 0, 0)          # Black for disconnected
        elif device_type == "widget":
            bg_color = (0, 0, 0)          # Black for clock/widgets
        elif is_on:
            bg_color = (0, 70, 0)         # Dark Green for ON state
        else:
            bg_color = (70, 0, 0)         # Dark Red for OFF state

        fg_color = (255, 255, 255)        # Always white for text, icons, and drawings

        # 2. Create a blank 196x196 image with the determined background color/gradient
        width, height = 196, 196
        if is_gradient:
            img = Image.new("RGB", (width, height))
            draw = ImageDraw.Draw(img)
            # Render horizontal gradient from left to right
            for x in range(width):
                factor = x / (width - 1)
                r = int(round(min_color[0] + (max_color[0] - min_color[0]) * factor))
                g = int(round(min_color[1] + (max_color[1] - min_color[1]) * factor))
                b = int(round(min_color[2] + (max_color[2] - min_color[2]) * factor))
                draw.line([(x, 0), (x, height)], fill=(r, g, b))
        else:
            img = Image.new("RGB", (width, height), color=bg_color)
            draw = ImageDraw.Draw(img)

        if is_gradient or is_weather_solid:
            # To ensure high contrast & elegant design, draw a translucent dark card container in the center
            try:
                overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.rounded_rectangle([12, 12, 184, 184], radius=16, fill=(0, 0, 0, 100))
                img.paste(overlay, (0, 0), overlay)
            except AttributeError:
                # Fallback if rounded_rectangle is not supported in the PIL version
                overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.rectangle([12, 12, 184, 184], fill=(0, 0, 0, 100))
                img.paste(overlay, (0, 0), overlay)

        # Render left-side vertical power bar if power_val is provided
        if power_val is not None:
            max_p = max_power if (max_power and max_power > 0) else 1000.0
            power_pct = min(100.0, max(0.0, (float(power_val) / float(max_p)) * 100.0))
            
            bar_x = 16
            bar_w = 12
            bar_top_y = 20
            bar_height = 156
            
            # Dark background track
            draw.rectangle([bar_x, bar_top_y, bar_x + bar_w, bar_top_y + bar_height], fill=(40, 40, 40))
            
            # Fill vertical bar from bottom-up using get_scale_color(power_pct)
            fill_h = int((power_pct / 100.0) * bar_height)
            if fill_h > 0:
                bar_color = get_scale_color(power_pct)
                fill_top_y = bar_top_y + bar_height - fill_h
                draw.rectangle([bar_x, fill_top_y, bar_x + bar_w, bar_top_y + bar_height], fill=bar_color)

        # 3. Render base icon (or default geometric symbol)
        icon_drawn = False
        if icon_path:
            # TODO(security): Validate icon_path to prevent Directory Traversal
            # Ensure it is treated as a safe path relative to project assets
            clean_icon_path = os.path.normpath(icon_path)
            if not clean_icon_path.startswith("..") and os.path.exists(clean_icon_path):
                try:
                    icon_img = Image.open(clean_icon_path).convert("RGBA")
                    # Scale down the icon beautifully to fit in center (90x90)
                    icon_img = icon_img.resize((80, 80), Image.Resampling.LANCZOS)
                    
                    # Convert the icon to always white (texts and icons are always white)
                    # By extracting alpha channel and building a solid white image with that alpha
                    if "A" in icon_img.mode:
                        r, g, b, a = icon_img.split()
                    else:
                        a = icon_img.convert("L")
                    white_channel = Image.new("L", icon_img.size, 255)
                    icon_img = Image.merge("RGBA", (white_channel, white_channel, white_channel, a))
                    
                    # Paste in the center
                    paste_x = (width - 80) // 2
                    paste_y = (height - 80) // 2 - 10 # Nudge slightly up
                    img.paste(icon_img, (paste_x, paste_y), icon_img)
                    icon_drawn = True
                except Exception as e:
                    logging.warning(f"DeckManager: Failed to render icon {icon_path}: {e}")

        # Fallback geometric shapes if no icon drawn
        if not icon_drawn:
            center_x, center_y = width // 2, height // 2 - 10
            r = 30
        # Render center text (large font, e.g. for temperature display) if provided
        if center_text:
            font_center = ImageFont.load_default(size=44)
            c_text_w = draw.textlength(center_text, font=font_center)
            stroke_w = 1 if (is_gradient or is_weather_solid) else 0
            stroke_f = (0, 0, 0) if (is_gradient or is_weather_solid) else None
            draw.text(((width - c_text_w) // 2, (height - 44) // 2 - 5), center_text, fill=fg_color, font=font_center, stroke_width=stroke_w, stroke_fill=stroke_f)

        # Fallback geometric shapes if no icon image was loaded
        if not icon_drawn and not center_text and (cpu_pct is None and mem_pct is None and temp_val is None):
            # Resolve the geometric shape to draw:
            # Check if icon_path is a known shape keyword, otherwise default to device_type
            shape_type = device_type
            if icon_path in ("light", "plug", "ceiling", "lamp", "3dprinter", "clock", "pc_monitor", "cpu", "gpu", "ram", "disk", "thermometer"):
                shape_type = icon_path

            center_x, center_y = width // 2, height // 2 - 10
            r = 30
            if shape_type == "thermometer":
                # High-contrast elegant thermometer drawing
                # Outer tube outline
                draw.rectangle([center_x - 6, center_y - 25, center_x + 6, center_y + 8], fill=None, outline=fg_color, width=2)
                # Outer tube rounded top cap
                draw.arc([center_x - 6, center_y - 30, center_x + 6, center_y - 20], start=180, end=360, fill=fg_color, width=2)
                # Outer bulb circle at bottom
                draw.ellipse([center_x - 12, center_y + 4, center_x + 12, center_y + 28], fill=None, outline=fg_color, width=2)
                # Inner mercury bulb fill
                draw.ellipse([center_x - 8, center_y + 8, center_x + 8, center_y + 24], fill=fg_color)
                # Inner mercury column
                draw.rectangle([center_x - 3, center_y - 12, center_x + 3, center_y + 12], fill=fg_color)
                # Temperature tick marks on the right side of tube
                draw.line([center_x + 9, center_y - 18, center_x + 14, center_y - 18], fill=fg_color, width=2)
                draw.line([center_x + 9, center_y - 8, center_x + 15, center_y - 8], fill=fg_color, width=2)
                draw.line([center_x + 9, center_y + 2, center_x + 14, center_y + 2], fill=fg_color, width=2)
            elif shape_type == "light":
                # Draw lightbulb outline/circle
                draw.ellipse([center_x - r, center_y - r, center_x + r, center_y + r], fill=None, outline=fg_color, width=3)
                # Small filament
                draw.line([center_x, center_y - 10, center_x, center_y + 10], fill=fg_color, width=3)
            elif shape_type == "ceiling":
                # Modern ceiling light fixture (canopy, stem, dome, and radiating light rays)
                # Ceiling canopy line
                draw.line([center_x - 25, center_y - 25, center_x + 25, center_y - 25], fill=fg_color, width=3)
                # Stem hanging down
                draw.line([center_x, center_y - 25, center_x, center_y - 12], fill=fg_color, width=3)
                # Dome/Half-circle shade
                draw.arc([center_x - 20, center_y - 12, center_x + 20, center_y + 12], start=180, end=360, fill=fg_color, width=3)
                # Close the shade bottom
                draw.line([center_x - 20, center_y, center_x + 20, center_y], fill=fg_color, width=3)
                # Radiating light rays underneath
                draw.line([center_x - 10, center_y + 8, center_x - 15, center_y + 20], fill=fg_color, width=2)
                draw.line([center_x, center_y + 10, center_x, center_y + 24], fill=fg_color, width=2)
                draw.line([center_x + 10, center_y + 8, center_x + 15, center_y + 20], fill=fg_color, width=2)
            elif shape_type == "lamp":
                # Elegant desk lamp/lampshade
                # Trapezoidal shade outline
                draw.line([center_x - 15, center_y - 20, center_x + 15, center_y - 20], fill=fg_color, width=3)
                draw.line([center_x - 25, center_y, center_x + 25, center_y], fill=fg_color, width=3)
                draw.line([center_x - 15, center_y - 20, center_x - 25, center_y], fill=fg_color, width=3)
                draw.line([center_x + 15, center_y - 20, center_x + 25, center_y], fill=fg_color, width=3)
                # Stem
                draw.line([center_x, center_y, center_x, center_y + 22], fill=fg_color, width=3)
                # Base
                draw.line([center_x - 15, center_y + 22, center_x + 15, center_y + 22], fill=fg_color, width=3)
            elif shape_type == "plug":
                # Draw plug rectangular shape
                draw.rectangle([center_x - r + 10, center_y - r + 15, center_x + r - 10, center_y + r - 5], fill=None, outline=fg_color, width=3)
                # Two prongs
                draw.line([center_x - 10, center_y - r, center_x - 10, center_y - r + 15], fill=fg_color, width=3)
                draw.line([center_x + 10, center_y - r, center_x + 10, center_y - r + 15], fill=fg_color, width=3)
            elif shape_type == "3dprinter":
                # Sleek, minimalist 3D printer outline
                # Outer rectangular frame / gantry
                draw.rectangle([center_x - 25, center_y - 25, center_x + 25, center_y + 25], fill=None, outline=fg_color, width=3)
                # Build bed / plate
                draw.line([center_x - 20, center_y + 15, center_x + 20, center_y + 15], fill=fg_color, width=3)
                # X-axis rail/gantry
                draw.line([center_x - 25, center_y - 5, center_x + 25, center_y - 5], fill=fg_color, width=2)
                # Printhead / extruder box
                draw.rectangle([center_x - 5, center_y - 5, center_x + 5, center_y + 3], fill=fg_color)
                # Extruding nozzle tip
                draw.line([center_x, center_y + 3, center_x, center_y + 7], fill=fg_color, width=2)
                # A 3D printed object outline resting on the bed
                draw.rectangle([center_x - 8, center_y + 8, center_x + 8, center_y + 15], fill=None, outline=fg_color, width=2)
            elif shape_type == "pc_monitor":
                # Elegant PC Tower Case
                draw.rectangle([center_x - 18, center_y - 25, center_x + 18, center_y + 25], fill=None, outline=fg_color, width=3)
                draw.rectangle([center_x - 12, center_y - 20, center_x + 12, center_y + 12], fill=None, outline=fg_color, width=2)
                draw.ellipse([center_x + 8, center_y + 18, center_x + 12, center_y + 22], fill=fg_color)
                draw.line([center_x - 12, center_y + 18, center_x + 4, center_y + 18], fill=fg_color, width=2)
            elif shape_type == "cpu":
                # High-tech CPU Microchip outline with pin connectors
                draw.rectangle([center_x - 18, center_y - 18, center_x + 18, center_y + 18], fill=None, outline=fg_color, width=3)
                draw.rectangle([center_x - 8, center_y - 8, center_x + 8, center_y + 8], fill=fg_color)
                for offset in [-12, 0, 12]:
                    draw.line([center_x - 24, center_y + offset, center_x - 18, center_y + offset], fill=fg_color, width=2)
                    draw.line([center_x + 18, center_y + offset, center_x + 24, center_y + offset], fill=fg_color, width=2)
                    draw.line([center_x + offset, center_y - 24, center_x + offset, center_y - 18], fill=fg_color, width=2)
                    draw.line([center_x + offset, center_y + 18, center_x + offset, center_y + 24], fill=fg_color, width=2)
            elif shape_type == "gpu":
                # High-end GPU board with cooler fans and PCIe connector
                draw.rectangle([center_x - 28, center_y - 16, center_x + 28, center_y + 16], fill=None, outline=fg_color, width=3)
                draw.ellipse([center_x - 18, center_y - 10, center_x - 2, center_y + 6], fill=None, outline=fg_color, width=2)
                draw.ellipse([center_x + 2, center_y - 10, center_x + 18, center_y + 6], fill=None, outline=fg_color, width=2)
                draw.line([center_x - 20, center_y + 20, center_x + 20, center_y + 20], fill=fg_color, width=3)
            elif shape_type == "ram":
                # RAM stick memory module with DRAM chips
                draw.rectangle([center_x - 28, center_y - 10, center_x + 28, center_y + 10], fill=None, outline=fg_color, width=3)
                for x_pos in [-20, -8, 4, 16]:
                    draw.rectangle([center_x + x_pos, center_y - 6, center_x + x_pos + 6, center_y + 6], fill=fg_color)
                draw.line([center_x - 28, center_y + 14, center_x + 28, center_y + 14], fill=fg_color, width=2)
            elif shape_type == "disk":
                # Elegant HDD disc platter and actuator arm
                draw.rectangle([center_x - 18, center_y - 24, center_x + 18, center_y + 24], fill=None, outline=fg_color, width=3)
                draw.ellipse([center_x - 14, center_y - 14, center_x + 14, center_y + 14], fill=None, outline=fg_color, width=2)
                draw.ellipse([center_x - 3, center_y - 3, center_x + 3, center_y + 3], fill=fg_color)
                draw.line([center_x + 10, center_y + 15, center_x + 2, center_y + 2], fill=fg_color, width=2)
            elif weather_type:
                self._draw_weather_icon(draw, center_x, center_y, weather_type, fg_color)
            else:
                # Clock dial
                draw.ellipse([center_x - r, center_y - r, center_x + r, center_y + r], fill=None, outline=fg_color, width=3)
                # Hands
                draw.line([center_x, center_y, center_x, center_y - r + 10], fill=fg_color, width=2)
                draw.line([center_x, center_y, center_x + r - 12, center_y], fill=fg_color, width=2)

        # 4. Render Label Text (at the top)
        # Using PIL default font scaled dynamically
        font_label = ImageFont.load_default(size=font_size_label)
        
        # Determine text stroke for high-contrast on gradients
        stroke_w = 1 if (is_gradient or is_weather_solid) else 0
        stroke_f = (0, 0, 0) if (is_gradient or is_weather_solid) else None

        # Draw label
        label_w = draw.textlength(label, font=font_label)
        draw.text(((width - label_w) // 2, margin_label), label, fill=fg_color, font=font_label, stroke_width=stroke_w, stroke_fill=stroke_f)

        # Render 3 vertical progress bars (CPU, MEM, TEMP) side-by-side if metrics are provided
        if cpu_pct is not None or mem_pct is not None or temp_val is not None:
            l1, l2, l3 = col_labels if (col_labels and len(col_labels) == 3) else ("CPU", "MEM", "TMP")
            columns_data = [
                (l1, cpu_pct, False, "%"),
                (l2, mem_pct, False, "%"),
                (l3, temp_val, True, "°C")
            ]

            # Layout metrics (196x196)
            col_width = 38
            col_gap = 20
            total_cols_width = (3 * col_width) + (2 * col_gap) # 114 + 40 = 154
            left_margin = (width - total_cols_width) // 2 # 21px

            font_col_title = ImageFont.load_default(size=18)
            font_col_val = ImageFont.load_default(size=22)

            bar_top_y = 65
            bar_height = 80

            for i, (c_label, val, is_t, unit) in enumerate(columns_data):
                col_x = left_margin + i * (col_width + col_gap)

                # 1. Render Top Column Title (CPU, MEM, TMP)
                title_w = draw.textlength(c_label, font=font_col_title)
                draw.text((col_x + (col_width - title_w) / 2, 42), c_label, fill=(220, 220, 220), font=font_col_title)

                # 2. Render Vertical Track (background)
                draw.rectangle([col_x, bar_top_y, col_x + col_width, bar_top_y + bar_height], fill=(40, 40, 40))

                # 3. Render Filled Vertical Bar (bottom-up) with interpolated solid color
                if val is not None:
                    if is_t:
                        # Temperature scale: 20°C (0% height) to 100°C (100% height)
                        pct_clamped = min(100.0, max(0.0, ((float(val) - 20.0) / (100.0 - 20.0)) * 100.0))
                    else:
                        # Standard usage % (0% to 100%)
                        pct_clamped = min(100.0, max(0.0, float(val)))

                    fill_h = int((pct_clamped / 100.0) * bar_height)
                    if fill_h > 0:
                        bar_color = get_scale_color(pct_clamped)
                        fill_top_y = bar_top_y + bar_height - fill_h
                        draw.rectangle([col_x, fill_top_y, col_x + col_width, bar_top_y + bar_height], fill=bar_color)

                # 4. Render Bottom Column Value (clean numbers only, e.g. "35", "62", "42")
                val_str = f"{int(round(val))}" if val is not None else "--"
                val_w = draw.textlength(val_str, font=font_col_val)
                draw.text((col_x + (col_width - val_w) / 2, bar_top_y + bar_height + 6), val_str, fill=(255, 255, 255), font=font_col_val)

        # 5. Render Status / Value Text (at the bottom)
        if cpu_pct is not None or mem_pct is not None or temp_val is not None:
            status_text = ""
        elif not reachable:
            status_text = "OFFLINE"
        elif text_override:
            status_text = text_override
        elif is_on:
            if device_type == "light" and brightness is not None:
                status_text = f"ON - {brightness}%"
            else:
                status_text = "ON"
        else:
            status_text = "OFF"

        font_status = ImageFont.load_default(size=font_size_status)
        status_w = draw.textlength(status_text, font=font_status)
        # Calculate vertically centered bottom offset relative to text height to prevent cutoff
        draw.text(((width - status_w) // 2, height - margin_status), status_text, fill=fg_color, font=font_status, stroke_width=stroke_w, stroke_fill=stroke_f)

        # 6. Save or push the rendering
        if self.simulator_mode:
            # Save as local PNG
            out_path = os.path.join(self.output_sim_dir, f"button_{index}.png")
            try:
                img.save(out_path)
                # We do not flood logs for the clock updates to keep terminal readable
                if device_type != "widget":
                    logging.info(f"DeckManager (SIM): Saved button {index} screen to -> {out_path}")
            except Exception as e:
                logging.error(f"DeckManager (SIM): Failed to save button {index} image: {e}")
        else:
            # Physical deck communication
            self._store_hw_image(index, img)

    def _store_hw_image(self, index: int, img):
        """
        Saves a rendered image for a grid cell into the icon cache and schedules the page upload.
        """
        try:
            # Clean up stale cached images for this button index to prevent disk accumulation.
            # Recent files are kept: a queued USB upload may still reference an older snapshot of this button.
            now_ms = int(time.time() * 1000)
            for filename in os.listdir(self.cache_dir):
                if filename.startswith(f"button_{index}_") and filename.endswith(".png"):
                    try:
                        file_ms = int(filename[len(f"button_{index}_"):-len(".png")])
                    except ValueError:
                        continue
                    if now_ms - file_ms < self.CACHE_GRACE_MS:
                        continue
                    try:
                        os.remove(os.path.join(self.cache_dir, filename))
                    except Exception as e:
                        logging.warning(f"DeckManager: Failed to delete old cached file {filename}: {e}")

            # Save the rendered Pillow image with a unique timestamp to bypass firmware caches
            timestamp = int(time.time() * 1000)
            icon_name = f"button_{index}_{timestamp}.png"
            img_path = os.path.join(self.cache_dir, icon_name)
            img.save(img_path)
            
            # Update our active buttons map
            self.active_buttons[index] = {
                'name': '',
                'icon': icon_name
            }
            
            # Trigger the hardware update
            self._hw_update_buttons()
        except Exception as e:
            logging.error(f"DeckManager (HW): Failed to update button {index} display: {e}")

    def close(self):
        """
        Safely disconnect from the physical deck.
        """
        if self.deck and self.has_hardware:
            try:
                self.deck.close()
                logging.info("DeckManager: Disconnected from Ulanzi D200.")
            except Exception as e:
                logging.error(f"DeckManager: Error during close: {e}")
