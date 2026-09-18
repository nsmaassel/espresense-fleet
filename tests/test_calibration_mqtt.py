"""Actual Paho/CLI integration against a disposable synthetic loopback broker."""
import importlib.util
import json
import os
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from tooling.calibration.records import load_log

ROOT = Path(__file__).resolve().parents[1]
try:
    HAS_PAHO = importlib.util.find_spec("paho.mqtt.client") is not None
except ModuleNotFoundError:
    HAS_PAHO = False


def receive_exact(connection, length):
    result = b""
    while len(result) < length:
        chunk = connection.recv(length - len(result))
        if not chunk:
            raise EOFError("Synthetic broker connection closed before the expected packet")
        result += chunk
    return result


def receive_packet(connection):
    header = receive_exact(connection, 1)[0]
    remaining, multiplier = 0, 1
    for _ in range(4):
        digit = receive_exact(connection, 1)[0]
        remaining += (digit & 127) * multiplier
        if digit < 128:
            if remaining > 16_384:
                raise ValueError("Unexpectedly large test MQTT packet")
            return header, receive_exact(connection, remaining)
        multiplier *= 128
    raise ValueError("Invalid test MQTT packet length")


def packet(header, payload):
    remaining, encoded = len(payload), bytearray()
    while True:
        digit = remaining % 128
        remaining //= 128
        encoded.append(digit | (128 if remaining else 0))
        if not remaining:
            return bytes([header]) + encoded + payload


class SyntheticBroker:
    """Small MQTT 3.1.1 fixture; sockets, worker and client all have deadlines."""

    def __init__(self, disconnect):
        self.disconnect = disconnect
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(10)
        self.port = self.listener.getsockname()[1]
        self.connection = None
        self.errors = queue.Queue()
        self.subscriptions = []
        self.finished = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        try:
            self.connection, _ = self.listener.accept()
            with self.connection as connection:
                connection.settimeout(5)
                header, _ = receive_packet(connection)
                if header != 0x10:
                    raise AssertionError("Expected CONNECT")
                connection.sendall(b"\x20\x02\x00\x00")
                header, data = receive_packet(connection)
                if header != 0x82:
                    raise AssertionError("Expected SUBSCRIBE")
                offset = 2
                while offset < len(data):
                    length = int.from_bytes(data[offset:offset + 2], "big")
                    self.subscriptions.append(data[offset + 2:offset + 2 + length].decode())
                    offset += 3 + length
                connection.sendall(packet(0x90, data[:2] + bytes(len(self.subscriptions))))
                topic = b"espresense/devices/example-phone/fictional-a"
                payload = json.dumps({"distance": 1.5, "rssi": -65, "int": 777,
                                      "name": "synthetic-private-marker", "mac": "drop-this-marker",
                                      "ip": "synthetic.invalid"}).encode()
                body = len(topic).to_bytes(2, "big") + topic + payload
                # Retained delivery is excluded even when its payload looks useful.
                connection.sendall(packet(0x31, body) + packet(0x30, body))
                if not self.disconnect:
                    header, data = receive_packet(connection)
                    if header != 0xE0 or data:
                        raise AssertionError("Expected clean DISCONNECT, never a client PUBLISH")
        except Exception as error:
            self.errors.put(error)
        finally:
            self.finished.set()

    def close(self):
        for connection in (self.connection, self.listener):
            if connection is not None:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
        self.thread.join(3)


@unittest.skipUnless(HAS_PAHO, "Optional MQTT integration: install requirements-capture.txt; Python CI installs it")
class CalibrationMqttTests(unittest.TestCase):
    def run_cli_capture(self, disconnect):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            schedule = {"schema": 1, "window_ms": 500, "nodes": {"node01": "room01"},
                        "stops": [{"room": "room01", "start_ms": 0, "end_ms": 1001}]}
            config = {"schema": 1, "device_alias": "example-phone", "node_map": {"fictional-a": "node01"}}
            (folder / "schedule.json").write_text(json.dumps(schedule), encoding="utf-8")
            (folder / "capture.json").write_text(json.dumps(config), encoding="utf-8")
            output = folder / "capture.jsonl"
            broker = SyntheticBroker(disconnect)
            broker.thread.start()
            try:
                # Do not send operator credentials to the test broker.
                environment = {key: value for key, value in os.environ.items()
                               if not key.startswith("ESPRESENSE_MQTT_")}
                environment.update(ESPRESENSE_MQTT_HOST="127.0.0.1", ESPRESENSE_MQTT_PORT=str(broker.port))
                result = subprocess.run(
                    [sys.executable, "-m", "tooling.calibration", "capture", "--config", str(folder / "capture.json"),
                     "--schedule", str(folder / "schedule.json"), "--duration-ms", "1001", "--output", str(output)],
                    cwd=ROOT, env=environment, capture_output=True, text=True, timeout=15)
                self.assertTrue(broker.finished.wait(2), "Synthetic broker did not finish")
                if not broker.errors.empty():
                    raise broker.errors.get_nowait()
                self.assertEqual(set(broker.subscriptions), {
                    "espresense/devices/example-phone/fictional-a", "espresense/rooms/fictional-a/telemetry"})
                self.assertEqual(result.returncode, 1 if disconnect else 0, result.stderr)
                self.assertEqual(result.stdout.count("elapsed time zero starts now"), 1)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(output.with_name(output.name + ".partial").exists())
                text = output.read_text(encoding="utf-8")
                for raw_value in ("synthetic-private-marker", "drop-this-marker", "synthetic.invalid",
                                  "example-phone", "fictional-a", "espresense/"):
                    self.assertNotIn(raw_value, text + result.stdout + result.stderr)
                log = load_log(output)
                self.assertEqual(log["capture"]["complete"], not disconnect)
                self.assertEqual(log["capture"]["retained"], 1)
                self.assertEqual(len(log["records"]), 1)
                row = dict(log["records"][0])
                elapsed = row.pop("elapsed_ms")
                self.assertGreaterEqual(elapsed, 0)
                self.assertLess(elapsed, 1001)
                self.assertEqual(row, {"schema": 1, "kind": "device", "node": "node01", "distance_m": 1.5, "rssi_dbm": -65})
                return log["capture"]
            finally:
                broker.close()
                self.assertFalse(broker.thread.is_alive(), "Synthetic broker thread leaked")

    def test_actual_paho_suback_duration_and_normalized_private_output(self):
        capture = self.run_cli_capture(disconnect=False)
        self.assertEqual(capture["reason"], "duration")
        self.assertEqual(capture["elapsed_ms"], 1001)

    def test_actual_paho_disconnect_yields_replayable_incomplete_output(self):
        capture = self.run_cli_capture(disconnect=True)
        self.assertIn(capture["reason"], ("disconnect", "transport"))
        self.assertLess(capture["elapsed_ms"], 1001)


if __name__ == "__main__":
    unittest.main()
