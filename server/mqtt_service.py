import logging
import json
import threading
import time
from typing import Dict, Any, Optional, Callable

try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False
    mqtt = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def parse_tasmota_payload(payload_str: str) -> Dict[str, Any]:
    """
    Parses Tasmota MQTT telemetry JSON string and extracts temperature and humidity.
    Supports common Tasmota sensor sub-keys (e.g. AM2301, DHT11, BME280, SHT3X, DS18B20, etc.)
    or flat JSON structures.
    """
    result = {
        "temperature": None,
        "humidity": None,
        "raw": None
    }
    
    if not payload_str:
        return result

    try:
        data = json.loads(payload_str)
        result["raw"] = data
        if isinstance(data, (int, float)):
            result["temperature"] = float(data)
            return result
        if not isinstance(data, dict):
            return result
    except (json.JSONDecodeError, TypeError):
        # Fallback if payload is a raw numeric string
        try:
            val = float(payload_str)
            result["temperature"] = val
            return result
        except ValueError:
            return result

    temp_keys = {"temperature", "temp", "temp_c", "temp_celsius"}
    hum_keys = {"humidity", "hum", "humidity_pct"}

    def extract_from_dict(d: dict):
        temp_val = None
        hum_val = None

        for k, v in d.items():
            k_lower = str(k).lower()
            if k_lower in temp_keys and isinstance(v, (int, float)):
                temp_val = float(v)
            elif k_lower in hum_keys and isinstance(v, (int, float)):
                hum_val = float(v)
            elif isinstance(v, dict):
                # Search sub-dictionaries (e.g., d["AM2301"])
                sub_t, sub_h = extract_from_dict(v)
                if sub_t is not None and temp_val is None:
                    temp_val = sub_t
                if sub_h is not None and hum_val is None:
                    hum_val = sub_h

        return temp_val, hum_val

    t, h = extract_from_dict(data)
    result["temperature"] = t
    result["humidity"] = h

    return result


class MqttService:
    """
    MQTT Service for subscribing to Tasmota and generic MQTT sensor topics with authentication.
    Handles background connection, reconnection, and thread-safe topic payload parsing.
    """
    def __init__(self, broker: str = "", port: int = 1883, username: str = "", password: str = "", enabled: bool = True):
        self.broker = broker.strip() if broker else ""
        self.port = int(port) if port else 1883
        self.username = username.strip() if username else ""
        self.password = password if password else ""
        self.enabled = enabled and bool(self.broker)
        
        self.client = None
        self.subscribed_topics: Dict[str, list] = {}
        self.latest_data: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.connected = False

    def start(self):
        """
        Starts the MQTT background client loop if enabled and paho-mqtt is installed.
        """
        if not self.enabled:
            logging.info("MqttService: MQTT service is disabled or no broker configured.")
            return

        if not PAHO_AVAILABLE:
            logging.warning("MqttService: paho-mqtt library is not installed. MQTT service operating in offline mode.")
            return

        try:
            # Handle paho-mqtt 2.x and 1.x compatibility
            try:
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
            except AttributeError:
                self.client = mqtt.Client()

            if self.username:
                self.client.username_pw_set(self.username, self.password)

            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            logging.info(f"MqttService: Connecting to MQTT broker {self.broker}:{self.port}...")
            self.client.connect_async(self.broker, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logging.error(f"MqttService: Failed to initialize MQTT client: {e}")

    def stop(self):
        """
        Stops the MQTT client loop and disconnects.
        """
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception as e:
                logging.error(f"MqttService: Error stopping client: {e}")

    def register_topic(self, topic: str, callback: Optional[Callable[[str, Dict[str, Any]], None]] = None):
        """
        Registers a topic to subscribe to and optional callback when data updates.
        """
        if not topic:
            return

        topic = topic.strip()
        with self._lock:
            if topic not in self.subscribed_topics:
                self.subscribed_topics[topic] = []
            if callback and callback not in self.subscribed_topics[topic]:
                self.subscribed_topics[topic].append(callback)

        # If already connected, subscribe immediately
        if self.client and self.connected:
            try:
                self.client.subscribe(topic)
                logging.info(f"MqttService: Subscribed to topic: {topic}")
            except Exception as e:
                logging.error(f"MqttService: Failed to subscribe to {topic}: {e}")

    def get_latest_data(self, topic: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the latest parsed sensor data for a topic.
        """
        with self._lock:
            return self.latest_data.get(topic)

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info("MqttService: Connected to MQTT broker successfully.")
            self.connected = True
            with self._lock:
                topics_to_sub = list(self.subscribed_topics.keys())
            for topic in topics_to_sub:
                try:
                    client.subscribe(topic)
                    logging.info(f"MqttService: Subscribed to topic: {topic}")
                except Exception as e:
                    logging.error(f"MqttService: Failed to subscribe to {topic}: {e}")
        else:
            logging.error(f"MqttService: Failed to connect to MQTT broker, return code: {rc}")
            self.connected = False

    def _on_disconnect(self, client, userdata, rc):
        logging.warning(f"MqttService: Disconnected from MQTT broker (rc: {rc}). Reconnecting automatically...")
        self.connected = False

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload_str = msg.payload.decode("utf-8", errors="ignore").strip()
            parsed = parse_tasmota_payload(payload_str)
            parsed["updated_at"] = time.time()

            callbacks = []
            with self._lock:
                self.latest_data[topic] = parsed
                if topic in self.subscribed_topics:
                    callbacks = list(self.subscribed_topics[topic])

            for cb in callbacks:
                try:
                    cb(topic, parsed)
                except Exception as e:
                    logging.error(f"MqttService: Exception in topic callback for {topic}: {e}")
        except Exception as e:
            logging.error(f"MqttService: Error processing MQTT message on {topic}: {e}")
