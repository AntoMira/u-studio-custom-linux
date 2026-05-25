import os
import logging
import time
import threading
import asyncio
from PIL import Image, ImageDraw, ImageFont

# Set up logging format
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class DeckManager:
    """
    Manages communication with the Ulanzi D200 Stream Deck.
    Features a robust Simulator Mode that saves button screens as PNG images for visual verification.
    """
    def __init__(self, simulator_mode: bool = False, font_size_label: int = 12, font_size_status: int = 10, margin_label: int = 10, margin_status: int = 25, small_window_mode: int = 0):
        self.simulator_mode = simulator_mode
        self.has_hardware = not self.simulator_mode
        self.deck = None
        self.callbacks = []
        self.output_sim_dir = "/home/zee/code/streamdeck/output_sim"
        self.cache_dir = "/home/zee/code/streamdeck/.cache/icons/_generated"
        self.font_size_label = font_size_label
        self.font_size_status = font_size_status
        self.margin_label = margin_label
        self.margin_status = margin_status
        self.small_window_mode = small_window_mode
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
        
        # Connect to hardware in loop context
        from strmdck.device_manager import auto_connect
        self.deck = auto_connect()
        if not self.deck:
            logging.error("DeckManager: Ulanzi D200 Stream Deck hardware not found on USB!")
            os._exit(1)
            
        logging.info("DeckManager: Physical Ulanzi D200 Stream Deck connected successfully!")
        
        # Start small screen reset sequence task inside running event loop
        self.loop.create_task(self._async_small_screen_reset())

        # Start reading key packets
        self.loop.create_task(self._hw_read_loop())
        
        # Start keep alive / small window updater
        self.loop.create_task(self._hw_keep_alive_loop())
        
        # Schedule brightness set after loop starts running
        self.loop.call_soon(self.deck.set_brightness, 80, True)
        self.loop.run_forever()

    async def _hw_read_loop(self):
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
            self.deck.set_buttons(buttons, update_only=update_only)
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

    def _on_hardware_keypress(self, key_index: int, pressed: bool):
        """
        Internal handler for hardware button events.
        Only triggers action on key release/press as configured.
        """
        if pressed:
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

            self._trigger_callbacks(key_index)

    def simulate_press(self, button_index: int):
        """
        Triggered in Simulator Mode to emulate pressing a button.
        """
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
            return # Discard simulated press!

        self._trigger_callbacks(button_index)

    def update_button(self, index: int, label: str, device_type: str, is_on: bool, brightness: int = None, icon_path: str = None, text_override: str = None, font_size_label: int = None, font_size_status: int = None, margin_label: int = None, margin_status: int = None, reachable: bool = True, weather_type: str = None):
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

        # 1. Determine Background Color based on State, Reachability, and Device Type
        if not reachable:
            bg_color = (0, 0, 0)          # Black for disconnected
        elif device_type == "widget":
            bg_color = (0, 0, 0)          # Black for clock/widgets
        elif is_on:
            bg_color = (0, 70, 0)         # Dark Green for ON state
        else:
            bg_color = (70, 0, 0)         # Dark Red for OFF state

        fg_color = (255, 255, 255)        # Always white for text, icons, and drawings

        # 2. Create a blank 196x196 image with the determined background color
        width, height = 196, 196
        img = Image.new("RGB", (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)

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
            if device_type == "light":
                # Draw lightbulb outline/circle
                draw.ellipse([center_x - r, center_y - r, center_x + r, center_y + r], fill=None, outline=fg_color, width=3)
                # Small filament
                draw.line([center_x, center_y - 10, center_x, center_y + 10], fill=fg_color, width=3)
            elif device_type == "plug":
                # Draw plug rectangular shape
                draw.rectangle([center_x - r + 10, center_y - r + 15, center_x + r - 10, center_y + r - 5], fill=None, outline=fg_color, width=3)
                # Two prongs
                draw.line([center_x - 10, center_y - r, center_x - 10, center_y - r + 15], fill=fg_color, width=3)
                draw.line([center_x + 10, center_y - r, center_x + 10, center_y - r + 15], fill=fg_color, width=3)
            elif weather_type:
                # Custom premium weather graphics
                if weather_type == "clear":
                    # Draw a glowing sun
                    sun_r = 18
                    draw.ellipse([center_x - sun_r, center_y - sun_r, center_x + sun_r, center_y + sun_r], fill=None, outline=fg_color, width=3)
                    # 8 radiating rays
                    import math
                    ray_len = 8
                    for angle in range(0, 360, 45):
                        rad = math.radians(angle)
                        x1 = center_x + (sun_r + 4) * math.cos(rad)
                        y1 = center_y + (sun_r + 4) * math.sin(rad)
                        x2 = center_x + (sun_r + 4 + ray_len) * math.cos(rad)
                        y2 = center_y + (sun_r + 4 + ray_len) * math.sin(rad)
                        draw.line([x1, y1, x2, y2], fill=fg_color, width=2)
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
                    draw.line([center_x - 10, center_y + 13, center_x - 13, center_y + 21], fill=fg_color, width=2)
                    draw.line([center_x, center_y + 13, center_x - 3, center_y + 21], fill=fg_color, width=2)
                    draw.line([center_x + 10, center_y + 13, center_x + 7, center_y + 21], fill=fg_color, width=2)
                elif weather_type == "thunderstorm":
                    # Cloud with lightning bolt
                    draw.ellipse([center_x - 22, center_y - 10, center_x - 5, center_y + 7], fill=fg_color)
                    draw.ellipse([center_x - 13, center_y - 23, center_x + 13, center_y + 7], fill=fg_color)
                    draw.ellipse([center_x + 5, center_y - 10, center_x + 22, center_y + 7], fill=fg_color)
                    draw.rectangle([center_x - 18, center_y - 2, center_x + 18, center_y + 7], fill=fg_color)
                    # Lightning zigzag
                    draw.line([center_x + 3, center_y + 11, center_x - 3, center_y + 17], fill=fg_color, width=2)
                    draw.line([center_x - 3, center_y + 17, center_x + 2, center_y + 17], fill=fg_color, width=2)
                    draw.line([center_x + 2, center_y + 17, center_x - 3, center_y + 24], fill=fg_color, width=2)
                elif weather_type == "snow":
                    # Cloud with snow crosses
                    draw.ellipse([center_x - 22, center_y - 10, center_x - 5, center_y + 7], fill=fg_color)
                    draw.ellipse([center_x - 13, center_y - 23, center_x + 13, center_y + 7], fill=fg_color)
                    draw.ellipse([center_x + 5, center_y - 10, center_x + 22, center_y + 7], fill=fg_color)
                    draw.rectangle([center_x - 18, center_y - 2, center_x + 18, center_y + 7], fill=fg_color)
                    # Snowflake crosses
                    draw.line([center_x - 10, center_y + 15, center_x - 6, center_y + 15], fill=fg_color, width=2)
                    draw.line([center_x - 8, center_y + 13, center_x - 8, center_y + 17], fill=fg_color, width=2)
                    draw.line([center_x + 8, center_y + 15, center_x + 4, center_y + 15], fill=fg_color, width=2)
                    draw.line([center_x + 6, center_y + 13, center_x + 6, center_y + 17], fill=fg_color, width=2)
                elif weather_type == "mist":
                    # Horizontal fog/breeze lines
                    draw.rectangle([center_x - 22, center_y - 9, center_x + 22, center_y - 6], fill=fg_color)
                    draw.rectangle([center_x - 13, center_y - 2, center_x + 18, center_y + 1], fill=fg_color)
                    draw.rectangle([center_x - 18, center_y + 5, center_x + 13, center_y + 8], fill=fg_color)
            else:
                # Clock dial
                draw.ellipse([center_x - r, center_y - r, center_x + r, center_y + r], fill=None, outline=fg_color, width=3)
                # Hands
                draw.line([center_x, center_y, center_x, center_y - r + 10], fill=fg_color, width=2)
                draw.line([center_x, center_y, center_x + r - 12, center_y], fill=fg_color, width=2)

        # 4. Render Label Text (at the top)
        # Using PIL default font scaled dynamically
        font_label = ImageFont.load_default(size=font_size_label)
        
        # Draw label
        label_w = draw.textlength(label, font=font_label)
        draw.text(((width - label_w) // 2, margin_label), label, fill=fg_color, font=font_label)

        # 5. Render Status / Value Text (at the bottom)
        if not reachable:
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
        draw.text(((width - status_w) // 2, height - margin_status), status_text, fill=fg_color, font=font_status)

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
            try:
                # Clean up old cached images for this button index to prevent disk accumulation
                for filename in os.listdir(self.cache_dir):
                    if filename.startswith(f"button_{index}_") and filename.endswith(".png"):
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
