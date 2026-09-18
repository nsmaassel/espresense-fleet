"""CLI acceptance against stateful loopback firmware doubles; never real nodes."""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import parse_qs

import yaml

from tooling.fleet.transport import NodeError, Transport


ROOT = Path(__file__).resolve().parents[1]


class Device:
    def __init__(self):
        self.state = {
            "main": {"room": "old", "mqtt_host": "broker.example", "mqtt_port": 1883,
                     "wifi-password": "***###***", "mqtt_pass": "***###***", "enabled": True},
            "hardware": {"led_1_type": "0", "led_1_cntrl": "0", "led_1_pin": 2, "led_1_cnt": 1},
            "extras": {"distance": 4.5},
        }
        self.requests = []
        self.forms = []
        self.fail_save = None
        self.ignore_save = False
        self.bad_endpoint = None
        self.restart_failure = False
        self.change_on_second_get = None
        self.read_counts = {}
        self.redirect = None
        device = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, code, body):
                self.send_response(code)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                device.requests.append(("GET", self.path))
                endpoint = self.path.removeprefix("/wifi/")
                if device.redirect:
                    self.send_response(302)
                    self.send_header("Location", device.redirect)
                    self.end_headers()
                    return
                device.read_counts[endpoint] = device.read_counts.get(endpoint, 0) + 1
                if device.bad_endpoint == endpoint:
                    self.respond(200, b'{"values": {"private": "DO-NOT-PRINT"}}')
                    return
                if device.change_on_second_get and device.read_counts[endpoint] == 2:
                    device.state[endpoint].update(device.change_on_second_get)
                self.respond(200, json.dumps({"defaults": device.state[endpoint], "values": {}}).encode())

            def do_POST(self):
                device.requests.append(("POST", self.path))
                if self.path == "/restart":
                    self.respond(500 if device.restart_failure else 200, b"DO-NOT-PRINT")
                    return
                endpoint = self.path.removeprefix("/wifi/")
                fields = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode(), keep_blank_values=True)
                device.forms.append((endpoint, fields))
                if device.fail_save == endpoint:
                    self.respond(500, b"DO-NOT-PRINT irk:0123456789abcdef")
                    return
                if not device.ignore_save:
                    for key, previous in list(device.state[endpoint].items()):
                        if isinstance(previous, bool):
                            device.state[endpoint][key] = key in fields
                        elif key in fields:
                            device.state[endpoint][key] = type(previous)(fields[key][0])
                self.respond(200, b"saved")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    @property
    def address(self):
        return f"127.0.0.1:{self.server.server_port}"

    def node(self, **kwargs):
        return {"id": "study", "address": self.address, "room": "study", **kwargs}


class FleetHTTPTests(unittest.TestCase):
    def run_cli(self, nodes, *args, json_output=True):
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Path(tmp) / "nodes.yaml"
            inventory.write_text(yaml.safe_dump({"nodes": nodes}), encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "tooling.fleet", *args[:1], str(inventory),
                                     *args[1:], *(["--json"] if json_output else []), "--timeout", "0.3", "--verify-timeout", "0.1",
                                     "--poll-interval", "0.01"], cwd=ROOT, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.stderr, "", result.stderr)
        self.assertNotIn("DO-NOT-PRINT", result.stdout)
        return result.returncode, json.loads(result.stdout) if json_output else result.stdout

    def test_diff_and_preview_never_write(self):
        with Device() as device:
            for command in ("diff", "apply"):
                code, report = self.run_cli([device.node()], command)
                self.assertEqual(code, 1)
                self.assertEqual(report["preview"], command == "apply")
                self.assertEqual(report["nodes"][0]["changes"], {"main": {"room": {"before": "old", "after": "study"}}})
            self.assertTrue(all(method == "GET" for method, _ in device.requests))

    def test_apply_preserves_credentials_and_unmanaged_settings_then_is_idempotent(self):
        with Device() as device:
            node = device.node(settings={"main": {"enabled": False},
                                        "hardware": {"led_1_type": "2", "led_1_cntrl": "1", "led_1_pin": 35},
                                        "extras": {"distance": 3.5}})
            code, report = self.run_cli([node], "apply", "--yes")
            self.assertEqual(code, 0, report)
            self.assertEqual(report["nodes"][0]["status"], "converged")
            self.assertFalse(device.state["main"]["enabled"])
            self.assertEqual(device.state["main"]["mqtt_host"], "broker.example")
            self.assertEqual(device.forms[0][1]["wifi-password"], ["***###***"])
            self.assertNotIn("enabled", device.forms[0][1])
            self.assertEqual(device.requests.count(("POST", "/restart")), 1)
            before = copy.deepcopy(device.forms)
            self.assertEqual(self.run_cli([node], "diff")[0], 0)
            self.assertEqual(self.run_cli([node], "apply", "--yes")[0], 0)
            self.assertEqual(device.forms, before)

    def test_numeric_dropdown_requires_quoted_desired_string_with_actionable_error(self):
        with Device() as device:
            code, report = self.run_cli([device.node(settings={"hardware": {"led_1_type": 2}})], "apply", "--yes")
            self.assertEqual(code, 2)
            self.assertEqual(report["nodes"][0]["error"], "hardware.led_1_type requires a string")
            self.assertEqual(device.forms, [])

    def test_independent_good_node_converges_when_another_node_fails(self):
        with Device() as device, Device() as broken:
            broken.bad_endpoint = "main"
            code, report = self.run_cli([broken.node(id="broken"), device.node()], "apply", "--yes")
            self.assertEqual(code, 2)
            self.assertEqual([node["status"] for node in report["nodes"]], ["error", "converged"])
            self.assertEqual(device.state["main"]["room"], "study")

    def test_unencodable_managed_live_value_is_not_rendered_in_human_diff(self):
        with Device() as device:
            device.state["main"]["room"] = "\ud800"
            code, output = self.run_cli([device.node()], "diff", json_output=False)
            self.assertEqual(code, 2)
            self.assertIn("unsupported live settings", output)
            self.assertNotIn("Traceback", output)
            self.assertEqual(device.forms, [])

    def test_unencodable_live_string_fails_preflight_without_hiding_good_node(self):
        with Device() as device, Device() as broken:
            broken.state["main"]["unmanaged"] = "\ud800"
            nodes = [broken.node(id="broken"), device.node()]
            for command in ("diff", "apply"):
                code, report = self.run_cli(nodes, command, "--yes")
                self.assertEqual(code, 2)
                self.assertEqual(report["nodes"][0]["status"], "error")
                self.assertEqual(broken.forms, [])
                self.assertEqual(report["nodes"][1]["status"], "converged" if command == "apply" else "drift")
            self.assertEqual(device.state["main"]["room"], "study")

    def test_unencodable_form_is_a_sanitized_transport_error_before_any_request(self):
        with Device() as device:
            with self.assertRaisesRegex(NodeError, "cannot encode settings form"):
                Transport(device.address).save("main", [("room", "\ud800")])
            self.assertEqual(device.requests, [])

    def test_refresh_preserves_concurrent_unmanaged_edit(self):
        with Device() as device:
            device.change_on_second_get = {"mqtt_host": "changed.example"}
            code, report = self.run_cli([device.node()], "apply", "--yes", "--no-restart")
            self.assertEqual(code, 0, report)
            self.assertEqual(device.state["main"]["mqtt_host"], "changed.example")
            self.assertEqual(report["nodes"][0]["restart"], "pending")
            self.assertEqual(report["nodes"][0]["verification"], "stored")
            self.assertNotIn(("POST", "/restart"), device.requests)

    def test_bad_second_endpoint_prevents_all_node_writes(self):
        with Device() as device:
            for settings in ({"hardware": {"unknown": 4}}, {"hardware": {"led_1_pin": 1.5}},
                             {"hardware": {"led_1_pin": True}}, {"main": {"enabled": "false"}}):
                code, report = self.run_cli([device.node(settings=settings)], "apply", "--yes")
                self.assertEqual(code, 2, report)
                self.assertFalse(device.forms)
            device.bad_endpoint = "hardware"
            self.assertEqual(self.run_cli([device.node(settings={"hardware": {"led_1_pin": 35}})], "apply", "--yes")[0], 2)
            self.assertFalse(device.forms)

    def test_entire_inventory_validates_before_any_read_even_when_selected(self):
        with Device() as device:
            code, report = self.run_cli([device.node(), {"id": "bad", "settings": {"main": {"mqtt_pass": "DO-NOT-PRINT"}}}],
                                        "apply", "--yes", "--node", "study")
            self.assertEqual(code, 2)
            self.assertEqual(report["nodes"], [])
            self.assertEqual(device.requests, [])

    def test_redirect_never_reaches_other_node(self):
        with Device() as device, Device() as target:
            device.redirect = f"http://{target.address}/wifi/main"
            code, report = self.run_cli([device.node()], "apply", "--yes")
            self.assertEqual(code, 2)
            self.assertEqual(target.requests, [])
            self.assertEqual(device.forms, [])

    def test_nonfinite_and_nested_live_values_prevent_writes(self):
        with Device() as device:
            for value in (float("nan"), {"nested": 1}):
                device.state["main"]["extra"] = value
                code, report = self.run_cli([device.node()], "apply", "--yes")
                self.assertEqual(code, 2)
                self.assertEqual(device.forms, [])

    def test_credential_embedded_in_managed_live_field_is_redacted(self):
        with Device() as device:
            device.state["main"]["room"] = "IRK:0123456789abcdef\nroom"
            code, report = self.run_cli([device.node()], "diff")
            self.assertEqual(code, 1)
            self.assertEqual(report["nodes"][0]["changes"]["main"]["room"]["before"], "irk:***?room")

    def test_refreshed_already_converged_endpoint_is_not_written(self):
        with Device() as device:
            device.change_on_second_get = {"room": "study"}
            code, report = self.run_cli([device.node()], "apply", "--yes")
            self.assertEqual(code, 0)
            self.assertEqual(device.forms, [])
            self.assertNotIn(("POST", "/restart"), device.requests)

    def test_partial_failure_does_not_retry_or_restart(self):
        with Device() as device:
            device.fail_save = "hardware"
            code, report = self.run_cli([device.node(settings={"hardware": {"led_1_pin": 35}})], "apply", "--yes")
            self.assertEqual(code, 2)
            self.assertEqual(report["nodes"][0]["status"], "partial")
            self.assertEqual(report["nodes"][0]["restart"], "pending")
            self.assertEqual(device.state["main"]["room"], "study")
            self.assertEqual(len(device.forms), 2)
            self.assertNotIn(("POST", "/restart"), device.requests)

    def test_ignored_save_and_restart_failure_are_not_success(self):
        with Device() as device:
            device.ignore_save = True
            code, report = self.run_cli([device.node()], "apply", "--yes")
            self.assertEqual(code, 2)
            self.assertEqual(report["nodes"][0]["verification"], "failed")
            device.ignore_save = False
            device.restart_failure = True
            code, report = self.run_cli([device.node()], "apply", "--yes")
            self.assertEqual(code, 2)
            self.assertEqual(report["nodes"][0]["restart"], "unconfirmed")

    def test_independent_nodes_and_empty_eligible_selection(self):
        with Device() as device:
            nodes = [device.node(), {"id": "broken", "address": "127.0.0.1:1", "room": "broken"}, {"id": "spare"}]
            code, report = self.run_cli(nodes, "diff")
            self.assertEqual(code, 2)
            self.assertEqual([node["status"] for node in report["nodes"]], ["drift", "error", "skipped"])
            self.assertEqual(self.run_cli(nodes, "diff", "--node", "spare")[0], 2)
            self.assertEqual(self.run_cli(nodes, "diff", "--node", "study")[0], 1)


if __name__ == "__main__":
    unittest.main()
