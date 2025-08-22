## Bambu Emulator Setup

### Generating SSL Certificate
To run the Bambu emulator with secure MQTT, you need to generate a self-signed SSL certificate and key. Use the following command in this directory:

```sh
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
-keyout mqtt_server.key -out mqtt_server.crt \
-config openssl_bambu_emulator.cnf -extensions v3_ca
```

This will create `mqtt_server.crt` and `mqtt_server.key` files for use by the emulator.

### About `bambu_simulator.py`
`bambu_simulator.py` is a Python script that emulates the behavior of a Bambu Lab printer's MQTT server. It allows you to test and develop integrations with the BLLEDController without needing a real printer. The script listens for MQTT connections, handles secure communication using the generated certificate, and simulates printer status and responses.

Typical uses:
- Test BLLEDController firmware and MQTT logic
- Simulate printer states and messages
- Develop and debug without a physical printer

Make sure to generate the certificate before running the emulator.
