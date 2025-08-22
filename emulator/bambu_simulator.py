import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
import time
import json
import ssl
import asyncio
import logging
import uuid
import hashlib
from amqtt.broker import Broker
from amqtt.client import MQTTClient
from amqtt.mqtt.constants import QOS_1

# === Configuration ===
# Generate session ID for this instance
SESSION_ID = "BAMBU1234"  # Hardcoded for demo
MQTT_USERNAME = "bblp"
MQTT_PASSWORD = SESSION_ID

BROKER_CONFIG = {
    'listeners': {
        'default': {
            'type': 'tcp',
            'bind': '0.0.0.0:1883'
        },
        'tls-listener': {
            'type': 'tcp',
            'bind': '0.0.0.0:8883',
            'ssl': True,
            'cafile': None,
            'certfile': 'mqtt_server.crt',
            'keyfile': 'mqtt_server.key'
        }
    }
}

class BambuLabSimulator:
    def __init__(self):
        # === Printer State ===
        self.printer_state = {
            "serial": "AC1260000000004",
            "chamber_light": "off",
            "work_light": "flashing",
            "door_open": False,
            "print_stage": -1,  # -1: idle, 0: printing, 1: bed_leveling, etc.
            "gcode_state": "IDLE",
            "hms_code": None,
            "bed_temp": 26.0,
            "bed_target_temp": 0.0,
            "nozzle_temp": 30.0,
            "nozzle_target_temp": 0.0,
            "progress": 0,
            "remaining_time": 0,
            "layer_num": 0,
            "total_layer_num": 0,
            "wifi_signal": "-51dBm",
            "nozzle_diameter": "0.4",
            "nozzle_type": "HX01",
            "fan_gear": 0,
            "spd_lvl": 2,
            "spd_mag": 100,
            "sequence_id": "2021"
        }
        
        # === MQTT ===
        self.broker = None
        self.client = None
        self.broker_task = None
        self.loop = None
        
        # === GUI ===
        self.setup_gui()
        
    def setup_gui(self):
        self.root = tk.Tk()
        self.root.title("Bambu Lab X1C MQTT Broker Simulator")
        self.root.geometry("800x600")
        
        # === Status Frame ===
        status_frame = tk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(status_frame, text="Broker Status:").grid(row=0, column=0, sticky="w")
        self.broker_status = tk.Label(status_frame, text="Stopped", fg="red")
        self.broker_status.grid(row=0, column=1, sticky="w")
        
        tk.Button(status_frame, text="Start Broker", command=self.start_broker).grid(row=0, column=2, padx=5)
        tk.Button(status_frame, text="Stop Broker", command=self.stop_broker).grid(row=0, column=3, padx=5)
        
        # === Printer Info ===
        info_frame = tk.LabelFrame(self.root, text="Connection Information")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Connection details in a grid
        tk.Label(info_frame, text="Serial:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        tk.Label(info_frame, text=self.printer_state['serial'], fg="green").grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        tk.Label(info_frame, text="MQTT Port:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", padx=5, pady=2)
        tk.Label(info_frame, text="1883 (anonymous access) 8883 (SSL with anonymous access)", fg="orange").grid(row=1, column=1, sticky="w", padx=5, pady=2)

        tk.Label(info_frame, text="Username:", font=("Arial", 10, "bold")).grid(row=2, column=0, sticky="w", padx=5, pady=2)
        username_label = tk.Label(info_frame, text=f"{MQTT_USERNAME} (not required)", fg="gray", font=("Courier", 10))
        username_label.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        
        tk.Label(info_frame, text="Password:", font=("Arial", 10, "bold")).grid(row=3, column=0, sticky="w", padx=5, pady=2)
        password_label = tk.Label(info_frame, text=f"{MQTT_PASSWORD} (not required)", fg="gray", font=("Courier", 10))
        password_label.grid(row=3, column=1, sticky="w", padx=5, pady=2)
        
        # Copy buttons
        tk.Button(info_frame, text="Copy Username", 
                 command=lambda: self.copy_to_clipboard(MQTT_USERNAME)).grid(row=2, column=2, padx=5, pady=2)
        tk.Button(info_frame, text="Copy Password", 
                 command=lambda: self.copy_to_clipboard(MQTT_PASSWORD)).grid(row=3, column=2, padx=5, pady=2)
        
        # === Control Panel ===
        control_frame = tk.LabelFrame(self.root, text="Printer Controls")
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Light controls
        light_frame = tk.Frame(control_frame)
        light_frame.pack(fill=tk.X, pady=2)
        tk.Label(light_frame, text="Chamber Light:").pack(side=tk.LEFT)
        tk.Button(light_frame, text="ON", command=lambda: self.set_light("on")).pack(side=tk.LEFT, padx=2)
        tk.Button(light_frame, text="OFF", command=lambda: self.set_light("off")).pack(side=tk.LEFT, padx=2)
        
        # Door controls
        door_frame = tk.Frame(control_frame)
        door_frame.pack(fill=tk.X, pady=2)
        tk.Label(door_frame, text="Door:").pack(side=tk.LEFT)
        tk.Button(door_frame, text="Open", command=lambda: self.set_door(True)).pack(side=tk.LEFT, padx=2)
        tk.Button(door_frame, text="Close", command=lambda: self.set_door(False)).pack(side=tk.LEFT, padx=2)
        
        # Print controls
        print_frame = tk.Frame(control_frame)
        print_frame.pack(fill=tk.X, pady=2)
        tk.Label(print_frame, text="Print:").pack(side=tk.LEFT)
        tk.Button(print_frame, text="Start", command=self.simulate_print).pack(side=tk.LEFT, padx=2)
        tk.Button(print_frame, text="Pause", command=lambda: self.set_print_state("PAUSE")).pack(side=tk.LEFT, padx=2)
        tk.Button(print_frame, text="Resume", command=lambda: self.set_print_state("RUNNING")).pack(side=tk.LEFT, padx=2)
        tk.Button(print_frame, text="Finish", command=lambda: self.set_print_state("FINISH")).pack(side=tk.LEFT, padx=2)
        
        # HMS Error simulation
        hms_frame = tk.LabelFrame(self.root, text="HMS Error Simulation")
        hms_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.hms_codes = {
            "Front Cover Removed": 0x0300120000020001,
            "First Layer Inspection": 0x0C0003000003000B,
            "Filament Runout": 0x0700200000030001,
            "Nozzle Temp Fail": 0x0300020000010001,
            "Bed Temp Fail": 0x0300010000010007,
            "Extruder Error": 0x0600100000010004,
        }
        
        for i, (name, code) in enumerate(self.hms_codes.items()):
            tk.Button(hms_frame, text=name, 
                     command=lambda c=code, n=name: self.trigger_hms(c, n)).grid(row=i//3, column=i%3, padx=2, pady=2)
        
        tk.Button(hms_frame, text="Clear HMS", command=self.clear_hms).grid(row=2, column=0, padx=2, pady=2)
        
        # === Log ===
        log_frame = tk.LabelFrame(self.root, text="MQTT Log")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()  # Required for clipboard to work
        self.log(f"📋 Copied to clipboard: {text}")
        
    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        
    def start_broker(self):
        if self.broker_task is None:
            self.loop = asyncio.new_event_loop()
            self.broker_task = threading.Thread(target=self._run_broker, daemon=True)
            self.broker_task.start()
            self.broker_status.config(text="Starting...", fg="orange")
            
    def _run_broker(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._async_broker())
        
    async def _async_broker(self):
        try:
            # Start broker with simple config first
            self.broker = Broker(BROKER_CONFIG)
            await self.broker.start()
            self.root.after(0, lambda: self.broker_status.config(text="Running", fg="green"))
            self.root.after(0, lambda: self.log("🚀 MQTT Broker started on port 1883 (insecure) and port 8883 (secure)"))
            self.root.after(0, lambda: self.log(f"🔑 Username: {MQTT_USERNAME}, Password: {MQTT_PASSWORD}"))
            
            # Wait a bit for broker to fully start
            await asyncio.sleep(2)
            
            # Start client for publishing
            self.client = MQTTClient()
            await self.client.connect('mqtt://localhost:1883')
            self.root.after(0, lambda: self.log("📡 Internal client connected"))
            
            # Start periodic status reporting
            asyncio.create_task(self._periodic_status())
            
            # Keep broker running
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ Broker error: {e}"))
            self.root.after(0, lambda: self.broker_status.config(text="Error", fg="red"))
            
    async def _periodic_status(self):
        while True:
            await self.publish_status()
            await asyncio.sleep(2)  # Send status every 2 seconds
            
    def stop_broker(self):
        if self.broker_task and self.loop:
            def cleanup():
                self.broker_task = None
                self.loop = None
                self.broker = None
                self.client = None
            async def shutdown():
                try:
                    if self.client:
                        await self.client.disconnect()
                    if self.broker:
                        await self.broker.shutdown()
                    self.root.after(0, lambda: self.broker_status.config(text="Stopped", fg="red"))
                    self.root.after(0, lambda: self.log("🛑 MQTT Broker stopped"))
                except Exception as e:
                    self.root.after(0, lambda: self.log(f"❌ Stop error: {e}"))
                    print_error(e)
                finally:
                    self.root.after(0, cleanup)
            self.loop.call_soon_threadsafe(lambda: asyncio.create_task(shutdown()))

    async def publish_status(self):
        if not self.client:
            return
            
        try:
            # Build status payload like real Bambu Lab printer - compatible with mqttmanager.h
            payload = {
                "print": {
                    "command": "push_status",  # REQUIRED by mqttmanager.h
                    "stg_cur": self.printer_state["print_stage"],
                    "gcode_state": self.printer_state["gcode_state"],
                    "home_flag": (1 << 23) if self.printer_state["door_open"] else -1067070056,
                    "lights_report": [
                        {"node": "chamber_light", "mode": self.printer_state["chamber_light"]},
                        {"node": "work_light", "mode": self.printer_state["work_light"]}
                    ],
                    "mc_percent": self.printer_state["progress"],
                    "mc_remaining_time": self.printer_state["remaining_time"],
                    "mc_print_stage": "1",
                    "mc_print_sub_stage": 0,
                    "percent": self.printer_state["progress"],
                    "remain_time": self.printer_state["remaining_time"],
                    "layer_num": self.printer_state["layer_num"],
                    "total_layer_num": self.printer_state["total_layer_num"],
                    "bed_temper": self.printer_state["bed_temp"],
                    "bed_target_temper": self.printer_state["bed_target_temp"],
                    "nozzle_temper": self.printer_state["nozzle_temp"],
                    "nozzle_target_temper": self.printer_state["nozzle_target_temp"],
                    "nozzle_diameter": self.printer_state["nozzle_diameter"],
                    "nozzle_type": self.printer_state["nozzle_type"],
                    "wifi_signal": self.printer_state["wifi_signal"],
                    "fan_gear": self.printer_state["fan_gear"],
                    "spd_lvl": self.printer_state["spd_lvl"],
                    "spd_mag": self.printer_state["spd_mag"],
                    "sequence_id": self.printer_state["sequence_id"],
                    "big_fan1_speed": "0",
                    "big_fan2_speed": "0",
                    "cooling_fan_speed": "0",
                    "heatbreak_fan_speed": "0",
                    "hw_switch_state": 0,
                    "xcam_status": "0",
                    "print_error": 0,
                    "print_gcode_action": 1,  # Added for mqttmanager compatibility
                    "print_real_action": 1,   # Added for mqttmanager compatibility
                    "fail_reason": "",        # Added for mqttmanager compatibility
                    "ams_status": 0,
                    "ams_rfid_status": 0,
                    "upgrade_state": {
                        "ahb_new_version_number": "",
                        "ams_new_version_number": "",
                        "consistency_request": False,
                        "dis_state": 0,
                        "err_code": 0,
                        "ext_new_version_number": "",
                        "force_upgrade": False,
                        "idx": 4,
                        "idx2": 267418057,
                        "lower_limit": "00.00.00.00",
                        "message": "",
                        "module": "",
                        "new_version_state": 2,
                        "ota_new_version_number": "",
                        "progress": "0",
                        "sequence_id": 0,
                        "sn": self.printer_state["serial"],
                        "status": "IDLE"
                    },
                    "ams": {
                        "ams": [],
                        "ams_exist_bits": "0",
                        "insert_flag": True,
                        "power_on_flag": False,
                        "tray_now": "255",
                        "version": 152
                    },
                    "ipcam": {
                        "ipcam_dev": "1",
                        "resolution": "1080p",
                        "timelapse": "disable"
                    }
                },
                "system": {
                    "command": "push_status"  # Added system section for compatibility
                }
            }
            
            # Add HMS if present
            if self.printer_state["hms_code"]:
                payload["print"]["hms"] = [{"attr": 0x00000000, "code": self.printer_state["hms_code"]}]
            else:
                payload["print"]["hms"] = []
                
            topic = f"device/{self.printer_state['serial']}/report"
            await self.client.publish(topic, json.dumps(payload).encode(), qos=QOS_1)
            
        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ Publish error: {e}"))
            print_error(e)
            
    def set_light(self, state):
        self.printer_state["chamber_light"] = state
        self.log(f"💡 Chamber light: {state.upper()}")
        
    def set_door(self, open_state):
        self.printer_state["door_open"] = open_state
        self.log(f"🚪 Door: {'OPEN' if open_state else 'CLOSED'}")
        
    def set_print_state(self, state):
        self.printer_state["gcode_state"] = state
        if state == "FINISH":
            self.printer_state["print_stage"] = -1
            self.printer_state["progress"] = 100
            self.printer_state["remaining_time"] = 0
        elif state == "PAUSE":
            self.printer_state["print_stage"] = 16
        elif state == "RUNNING" and self.printer_state["print_stage"] == 16:
            self.printer_state["print_stage"] = 0
        self.log(f"🖨️ Print state: {state}")
        
    def trigger_hms(self, code, name):
        self.printer_state["hms_code"] = code
        self.log(f"⚠️ HMS Error: {name}")
        
    def clear_hms(self):
        self.printer_state["hms_code"] = None
        self.log("✅ HMS Error cleared")
        
    def simulate_print(self):
        def _simulate():
            stages = [
                (1, "RUNNING", "Bed Leveling", 5),
                (14, "RUNNING", "Cleaning Nozzle", 10),
                (8, "RUNNING", "Extrusion Calibration", 15),
                (2, "RUNNING", "Preheating", 25),
                (0, "RUNNING", "Printing", 100)
            ]
            
            for stage, state, desc, progress in stages:
                self.printer_state["print_stage"] = stage
                self.printer_state["gcode_state"] = state
                self.printer_state["progress"] = progress
                self.printer_state["remaining_time"] = max(0, 3600 - (progress * 36))
                self.log(f"🖨️ {desc} ({progress}%)")
                time.sleep(3)
                
            self.set_print_state("FINISH")
            
        threading.Thread(target=_simulate, daemon=True).start()
        
    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.stop_broker()

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.WARNING)
    
    # Start simulator
    simulator = BambuLabSimulator()
    simulator.run()
