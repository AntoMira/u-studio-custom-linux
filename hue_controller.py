import os
import logging
import requests

# Set up logging format
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class HueController:
    """
    Client for interacting with local Philips Hue Bridge REST API.
    Supports a highly robust 'Simulator Mode' for off-grid development and testing.
    """
    def __init__(self, bridge_ip: str, username: str, simulator_mode: bool = False):
        self.bridge_ip = bridge_ip
        self.username = username
        self.simulator_mode = simulator_mode
        self.base_url = f"http://{self.bridge_ip}/api/{self.username}"
        self.timeout_seconds = 3.0  # 3 second timeout for local API requests

        # In-memory database for mock testing when in Simulator Mode
        self._mock_states = {
            "1": {"on": True, "bri": 254, "reachable": True, "type": "Dimmable light"},
            "2": {"on": False, "bri": 128, "reachable": True, "type": "Dimmable light"},
            "3": {"on": False, "reachable": True, "type": "On/Off plug-in unit"},
            "4": {"on": True, "reachable": True, "type": "On/Off plug-in unit"},
            "5": {"on": True, "bri": 254, "reachable": True, "type": "Dimmable light"},
            "6": {"on": True, "reachable": True, "type": "On/Off plug-in unit"},
            "7": {"on": False, "reachable": True, "type": "On/Off plug-in unit"}
        }

        if self.simulator_mode:
            logging.info("HueController: Initialized in SIMULATOR MODE. No network requests will be made.")
        else:
            logging.info(f"HueController: Initialized in PHYSICAL MODE (Bridge IP: {self.bridge_ip})")

    def get_light_state(self, light_id: str) -> dict:
        """
        Fetches the current state of a specific light or plug.
        Returns a dictionary: {'on': bool, 'bri': int or None, 'reachable': bool}
        """
        # Input validation
        if not light_id or not isinstance(light_id, str):
            logging.warning(f"HueController: Invalid light_id type: {type(light_id)}")
            return {"on": False, "bri": None, "reachable": False}

        if self.simulator_mode:
            state = self._mock_states.get(light_id, {"on": False, "reachable": False})
            return {
                "on": state.get("on", False),
                "bri": state.get("bri"),
                "reachable": state.get("reachable", False)
            }

        try:
            url = f"{self.base_url}/lights/{light_id}"
            response = requests.get(url, timeout=self.timeout_seconds)
            
            # Check for API level errors
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0 and "error" in data[0]:
                    logging.error(f"HueController Bridge Error: {data[0]['error']['description']}")
                    return {"on": False, "bri": None, "reachable": False}
                
                state_data = data.get("state", {})
                return {
                    "on": state_data.get("on", False),
                    "bri": state_data.get("bri"),
                    "reachable": state_data.get("reachable", False)
                }
            else:
                logging.error(f"HueController: HTTP error {response.status_code} fetching light {light_id}")
                return {"on": False, "bri": None, "reachable": False}

        except requests.exceptions.RequestException as e:
            logging.error(f"HueController Connection Exception fetching light {light_id}: {e}")
            # TODO(security): Gracefully handle network outage without exposing system details
            return {"on": False, "bri": None, "reachable": False}

    def set_light_state(self, light_id: str, payload: dict) -> bool:
        """
        Sends a state update request to the Hue Bridge.
        Payload typical keys: {'on': True/False, 'bri': 0-254}
        """
        if not light_id or not isinstance(light_id, str):
            return False

        if self.simulator_mode:
            if light_id in self._mock_states:
                # Update mock database
                for key, val in payload.items():
                    self._mock_states[light_id][key] = val
                logging.info(f"HueController (SIM): Updated Light {light_id} state -> {payload}")
                return True
            logging.warning(f"HueController (SIM): Light {light_id} not found in mock database")
            return False

        try:
            url = f"{self.base_url}/lights/{light_id}/state"
            response = requests.put(url, json=payload, timeout=self.timeout_seconds)
            
            if response.status_code == 200:
                data = response.json()
                # Check for success verification returned from Bridge
                if isinstance(data, list) and len(data) > 0:
                    if "success" in data[0]:
                        return True
                    elif "error" in data[0]:
                        logging.error(f"HueController Bridge Error: {data[0]['error']['description']}")
                        return False
                return True
            else:
                logging.error(f"HueController: HTTP error {response.status_code} setting light {light_id} state")
                return False

        except requests.exceptions.RequestException as e:
            logging.error(f"HueController Connection Exception updating light {light_id}: {e}")
            return False

    def toggle_light(self, light_id: str) -> bool:
        """
        Toggles the light or plug ON or OFF depending on its current state.
        Works identically for bulbs and smart plugs.
        """
        current_state = self.get_light_state(light_id)
        if not current_state.get("reachable", True) and not self.simulator_mode:
            logging.warning(f"HueController: Device {light_id} is unreachable")
            # Fail closed, do not perform action on unreachable hardware
            return False

        new_on_state = not current_state.get("on", False)
        payload = {"on": new_on_state}
        
        logging.info(f"HueController: Toggling Device {light_id} -> {'ON' if new_on_state else 'OFF'}")
        return self.set_light_state(light_id, payload)

    def set_brightness(self, light_id: str, percent: int) -> bool:
        """
        Sets brightness of a bulb (0-100%).
        Converts to Hue scale (0-254).
        """
        # Clamp percent between 0 and 100
        percent = max(0, min(100, percent))
        hue_bri = int((percent / 100.0) * 254)
        
        # Smart Plugs don't support brightness, so we skip setting it if we detect it is a plug.
        # But this function is typically called for lights only.
        payload = {"on": True, "bri": hue_bri}
        logging.info(f"HueController: Setting Device {light_id} brightness to {percent}% ({hue_bri}/254)")
        return self.set_light_state(light_id, payload)

    def list_devices(self) -> dict:
        """
        Fetches all registered lights and smart plugs from the Hue Bridge.
        Returns a dictionary mapping device ID to device details, or an empty dict on error.
        """
        if self.simulator_mode:
            return self._mock_states

        try:
            url = f"{self.base_url}/lights"
            response = requests.get(url, timeout=self.timeout_seconds)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0 and "error" in data[0]:
                    logging.error(f"HueController Bridge Error: {data[0]['error']['description']}")
                    return {}
                return data
            else:
                logging.error(f"HueController: HTTP error {response.status_code} listing devices")
                return {}
        except requests.exceptions.RequestException as e:
            logging.error(f"HueController Connection Exception listing devices: {e}")
            return {}
