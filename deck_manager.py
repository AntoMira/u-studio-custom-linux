import os
import logging
import time
from PIL import Image, ImageDraw, ImageFont

# Set up logging format
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

try:
    from strmdck import StreamDeck
    HAS_STRMDCK = True
except ImportError:
    HAS_STRMDCK = False

class DeckManager:
    """
    Manages communication with the Ulanzi D200 Stream Deck.
    Features a robust Simulator Mode that saves button screens as PNG images for visual verification.
    """
    def __init__(self, simulator_mode: bool = False):
        self.simulator_mode = simulator_mode
        self.has_hardware = HAS_STRMDCK and not self.simulator_mode
        self.deck = None
        self.callbacks = []
        self.output_sim_dir = "/home/zee/code/streamdeck/output_sim"

        if self.simulator_mode:
            logging.info("DeckManager: Initialized in SIMULATOR MODE. Generated images will be saved to output_sim/")
            # Create simulator output directory safely
            os.makedirs(self.output_sim_dir, exist_ok=True)
        else:
            if not HAS_STRMDCK:
                logging.warning("DeckManager: 'strmdck' library not found! Falling back to SIMULATOR MODE.")
                self.simulator_mode = True
                self.has_hardware = False
                os.makedirs(self.output_sim_dir, exist_ok=True)
            else:
                logging.info("DeckManager: Initializing physical Ulanzi D200 Stream Deck connection...")
                try:
                    # Initialize physical deck connection
                    self.deck = StreamDeck()
                    self.deck.open()
                    self.deck.set_brightness(80) # 80% default panel brightness
                    
                    # Set up hardware keypress callback
                    self.deck.set_key_callback(self._on_hardware_keypress)
                    logging.info("DeckManager: Physical Ulanzi D200 Stream Deck connected successfully!")
                except Exception as e:
                    logging.error(f"DeckManager: Failed to connect to physical Stream Deck: {e}. Falling back to SIMULATOR MODE.")
                    self.simulator_mode = True
                    self.has_hardware = False
                    os.makedirs(self.output_sim_dir, exist_ok=True)

    def register_callback(self, callback):
        """
        Registers a callback function to handle button presses.
        Callback signature: func(button_index: int)
        """
        self.callbacks.append(callback)

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
            self._trigger_callbacks(key_index)

    def simulate_press(self, button_index: int):
        """
        Triggered in Simulator Mode to emulate pressing a button.
        """
        logging.info(f"DeckManager (SIM): Emulating button press for index: {button_index}")
        self._trigger_callbacks(button_index)

    def update_button(self, index: int, label: str, device_type: str, is_on: bool, brightness: int = None, icon_path: str = None, text_override: str = None):
        """
        Draws the button image using Pillow and pushes it to the D200 key (or saves it in Simulator Mode).
        * index: Button index (0 to 12)
        * label: Label text displayed at the top of the button
        * device_type: 'light', 'plug', or 'widget'
        * is_on: True/False state
        * brightness: Brightness percentage (0-100) for dimmable lights
        * icon_path: Optional path to a base icon PNG
        * text_override: For widgets like clocks to display time directly (e.g., "15:20")
        """
        # Validate button index
        if index < 0 or index > 12:
            logging.error(f"DeckManager: Button index out of bounds: {index}")
            return

        # 1. Create a blank 196x196 image
        width, height = 196, 196
        img = Image.new("RGB", (width, height), color=(15, 15, 15)) # Ultra-premium dark background
        draw = ImageDraw.Draw(img)

        # 2. Determine Color Palette based on State
        if is_on:
            # Elegant warm yellow/orange glow for lights, turquoise for plugs, soft blue for clock
            if device_type == "light":
                glow_color = (255, 193, 7) # Warm Amber
                accent_color = (255, 235, 59)
            elif device_type == "plug":
                glow_color = (0, 150, 136) # Cool Teal
                accent_color = (128, 203, 196)
            else:
                glow_color = (33, 150, 243) # Soft Blue
                accent_color = (144, 202, 249)
            
            # Draw subtle glowing border
            draw.rectangle([0, 0, width-1, height-1], outline=glow_color, width=4)
        else:
            # Dim gray for off state
            glow_color = (55, 71, 79) # Charcoal
            accent_color = (120, 144, 156) # Cool Slate
            draw.rectangle([0, 0, width-1, height-1], outline=glow_color, width=2)

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
                    
                    # Apply color tint if off to look premium
                    if not is_on:
                        # Convert to grayscale and apply dim overlay
                        icon_img = icon_img.convert("L").convert("RGBA")
                    
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
                draw.ellipse([center_x - r, center_y - r, center_x + r, center_y + r], fill=None, outline=accent_color, width=3)
                # Small filament
                draw.line([center_x, center_y - 10, center_x, center_y + 10], fill=accent_color, width=3)
            elif device_type == "plug":
                # Draw plug rectangular shape
                draw.rectangle([center_x - r + 10, center_y - r + 15, center_x + r - 10, center_y + r - 5], fill=None, outline=accent_color, width=3)
                # Two prongs
                draw.line([center_x - 10, center_y - r, center_x - 10, center_y - r + 15], fill=accent_color, width=3)
                draw.line([center_x + 10, center_y - r, center_x + 10, center_y - r + 15], fill=accent_color, width=3)
            else:
                # Clock dial
                draw.ellipse([center_x - r, center_y - r, center_x + r, center_y + r], fill=None, outline=accent_color, width=3)
                # Hands
                draw.line([center_x, center_y, center_x, center_y - r + 10], fill=accent_color, width=2)
                draw.line([center_x, center_y, center_x + r - 12, center_y], fill=accent_color, width=2)

        # 4. Render Label Text (at the top)
        # Using PIL default font which is always available.
        # Fallback if no custom ttf font is used
        font = ImageFont.load_default()
        
        # Draw label
        label_w = draw.textlength(label, font=font)
        draw.text(((width - label_w) // 2, 10), label, fill=accent_color, font=font)

        # 5. Render Status / Value Text (at the bottom)
        status_text = "OFF"
        if text_override:
            status_text = text_override
        elif is_on:
            if device_type == "light" and brightness is not None:
                status_text = f"ON - {brightness}%"
            else:
                status_text = "ON"

        status_w = draw.textlength(status_text, font=font)
        draw.text(((width - status_w) // 2, height - 25), status_text, fill=(255, 255, 255) if is_on else (120, 144, 156), font=font)

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
                # Convert PIL Image to RGB bytes or native layout required by strmdck
                # Note: strmdck requires raw bytes or has a direct write_image method.
                # Let's inspect strmdck package behavior in execution phase.
                # For safety, we call the standard write method:
                raw_bytes = img.tobytes()
                self.deck.write_key_image(index, raw_bytes)
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
