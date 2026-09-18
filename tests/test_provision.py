import contextlib
import io
import unittest
from unittest.mock import patch
from tooling.provision import espresense_set as node


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {"defaults": {"enabled": True, "room": "", "mqtt_port": 1883,
                                 "wifi-password": ""},
                    "values": {"room": "test-room", "wifi-password": "***###***"}}

    def test_false_checkbox_override_is_absent_and_password_preserved(self):
        for value in (False, "false", "0", "off", "no"):
            with self.subTest(value=value):
                form = dict(node.build_form(self.cfg, {"enabled": value}))
                self.assertNotIn("enabled", form)
                self.assertEqual(form["wifi-password"], "***###***")

    def test_fresh_main_endpoint_allows_known_empty_password_fields(self):
        cfg = {"defaults": {"room": "test", "mqtt_port": 1883}, "values": {}}
        form = dict(node.build_form(cfg, {"wifi-password": "example", "mqtt_user": "example"}, endpoint="main"))
        self.assertEqual(form["wifi-password"], "example")
        with self.assertRaises(ValueError):
            node.build_form(cfg, {"mqtt_user": "example"}, endpoint="hardware")

    def test_true_checkbox_override_is_canonical(self):
        self.assertEqual(dict(node.build_form(self.cfg, {"enabled": "true"}))["enabled"], "1")

    def test_invalid_override_cannot_be_posted(self):
        for overrides in ({"typo": "x"}, {"enabled": "maybe"}, {"mqtt_port": "oops"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                node.build_form(self.cfg, overrides)

    def test_incomplete_or_nested_config_cannot_replace_node_settings(self):
        for cfg in ({}, {"defaults": {}, "values": {}}, {"defaults": [], "values": {}},
                    {"defaults": {"room": "x"}},
                    {"defaults": {"room": []}, "values": {}}):
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):
                node.build_form(cfg, {"room": "test"})

    def test_redacts_read_and_change_outputs_recursively(self):
        value = {"wifi-password": "secret", "mqtt_pass": "secret", "nested": {"api_token": "secret"}, "room": "test"}
        shown = node.redact(value)
        self.assertNotIn("secret", str(shown))
        self.assertEqual(shown["room"], "test")

    def test_cli_rejects_bad_arguments_before_network(self):
        for args in (["localhost", "bad"], ["localhost", "main", "room"],
                     ["localhost", "main", "--typo"], ["http://localhost", "main"]):
            with self.subTest(args=args), patch.object(node, "get") as get:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    node.main(args)
                get.assert_not_called()

    def test_update_posts_complete_form_and_no_restart_honors_flag(self):
        from urllib.parse import parse_qs
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.status = 200
        for args in (["localhost", "main", "enabled=false", "--no-restart"],
                     ["localhost", "main", "--no-restart", "enabled=false"]):
            with self.subTest(args=args), patch.object(node, "get", return_value=self.cfg), patch.object(node.urllib.request, "urlopen", return_value=response) as request:
                with contextlib.redirect_stdout(io.StringIO()):
                    node.main(args)
                form = parse_qs(request.call_args.args[0].data.decode(), keep_blank_values=True)
                self.assertNotIn("enabled", form)
                self.assertEqual(form["wifi-password"], ["***###***"])
                self.assertEqual(form["room"], ["test-room"])
                self.assertEqual(request.call_count, 1)

    def test_read_output_hides_actual_secrets(self):
        cfg = {"defaults": {}, "values": {"wifi-password": "sensitive-test-value", "room": "test"}}
        output = io.StringIO()
        with patch.object(node, "get", return_value=cfg), contextlib.redirect_stdout(output):
            node.main(["localhost", "main"])
        self.assertNotIn("sensitive-test-value", output.getvalue())
        self.assertIn("test", output.getvalue())

    def test_invalid_overrides_do_not_post(self):
        with patch.object(node, "get", return_value=self.cfg), patch.object(node.urllib.request, "urlopen") as request:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                node.main(["localhost", "main", "typo=value"])
            request.assert_not_called()


class WindowsProvisionTests(unittest.TestCase):
    def run_script(self, mode):
        import pathlib
        import shutil
        import subprocess
        if not shutil.which("pwsh"):
            self.skipTest("PowerShell is required for the offline Windows adapter tests")
        script = pathlib.Path(__file__).resolve().parents[1] / "tooling/provision/Setup-ESPresenseNode.ps1"
        harness = r"""
$global:calls = [System.Collections.Generic.List[string]]::new()
function netsh {
    $global:calls.Add(($args -join ' '))
    $global:LASTEXITCODE = 0
    if (($args -join ' ') -match 'add profile' -and 'MODE' -eq 'native') { $global:LASTEXITCODE = 1 }
    if (($args -join ' ') -match 'show interfaces') { '    SSID : espresense-abcdef' }
}
function Start-Sleep {}
function Invoke-RestMethod { throw 'DO-NOT-LEAK-server-body' }
try { & 'SCRIPT' -ApSsid espresense-abcdef -RoomName test -HomeSsid 'Test Home' -MqttHost localhost }
catch { Write-Output ('FAILED: ' + $_.Exception.Message) }
Write-Output ($global:calls -join [Environment]::NewLine)
""".replace("SCRIPT", str(script)).replace("MODE", mode)
        return subprocess.run(["pwsh", "-NoProfile", "-Command", harness], capture_output=True, text=True, timeout=15)

    def test_http_failure_still_reconnects_and_does_not_expose_response(self):
        result = self.run_script("http")
        self.assertIn("wlan connect name=Test Home", result.stdout)
        self.assertNotIn("DO-NOT-LEAK", result.stdout + result.stderr)

    def test_native_command_failure_is_fatal_and_still_reconnects(self):
        result = self.run_script("native")
        self.assertIn("FAILED:", result.stdout)
        self.assertIn("wlan connect name=Test Home", result.stdout)
        self.assertNotIn("wlan connect name=espresense", result.stdout)


    def test_fresh_node_provisions_with_escaped_ssid_and_checkbox_merge(self):
        import pathlib
        import shutil
        import subprocess
        if not shutil.which("pwsh"):
            self.skipTest("PowerShell is required for the offline Windows adapter tests")
        script = pathlib.Path(__file__).resolve().parents[1] / "tooling/provision/Setup-ESPresenseNode.ps1"
        harness = r"""
$global:xmlChecked = $false
$global:bodyChecked = $false
function netsh {
    $global:LASTEXITCODE = 0
    foreach ($item in $args) {
        if ($item -like 'filename=*') {
            [xml]$profile = Get-Content -LiteralPath $item.Substring(9) -Raw
            if ($profile.WLANProfile.name -ne 'test<&>') { throw 'XML mismatch' }
            $global:xmlChecked = $true
        }
    }
}
function Start-Sleep {}
function Read-Host { ConvertTo-SecureString 'fixture-secret' -AsPlainText -Force }
function Invoke-RestMethod {
    param($Uri, $Method, $Body, $ContentType, $TimeoutSec)
    if ($Method -eq 'Get') {
        return [pscustomobject]@{
            defaults = [pscustomobject]@{room=''; mqtt_port=1883; enabled=$true; other=$false}
            values = [pscustomobject]@{room='test'; enabled=$false; other=$true}
        }
    }
    if ($Uri -like '*/wifi/main') {
        if ($Body -match '(^|&)enabled=' -or $Body -notmatch '(^|&)other=1(&|$)' -or $Body -notmatch 'wifi-password=fixture-secret') {
            throw 'Form mismatch'
        }
        $global:bodyChecked = $true
    }
}
try {
    & 'SCRIPT' -ApSsid 'test<&>' -RoomName test -HomeSsid 'Test Home' -MqttHost localhost
    if (-not $global:xmlChecked -or -not $global:bodyChecked) { throw 'Missing operation' }
    Write-Output 'CHECKED'
} catch { Write-Output 'TEST FAILED'; exit 1 }
""".replace("SCRIPT", str(script))
        result = subprocess.run(["pwsh", "-NoProfile", "-Command", harness], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CHECKED", result.stdout)
        self.assertNotIn("fixture-secret", result.stdout + result.stderr)
