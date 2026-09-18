"""Repository policy tests use temporary git repositories and synthetic data only."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import unittest

from tooling.governance.check_repository import check_repository, scan_working_files


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.write('AGENTS.md', '# Development instructions\n')
        self.write('.specify/memory/constitution.md', '# Principles\n')
        self.write('specs/001-test/spec.md', '- **FR-001**: A requirement.\n')
        self.write('specs/001-test/plan.md', '## Constitution Check\nReview each principle.\n')
        self.write('specs/001-test/tasks.md', '- [ ] T001 Implement FR-001.\n')

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')

    def test_minimal_complete_spec_and_fictional_inventory_pass(self):
        self.write('examples/nodes.example.yaml', 'site: example-home\nbroker:\n  host: 192.0.2.20\nnodes:\n- mac: null\n  address: mqtt.example\n')
        self.assertEqual(check_repository(self.root), [])

    def test_ignored_private_file_is_checked_when_force_tracked(self):
        self.write('.gitignore', '/private/\n')
        self.write('private/house.yaml', 'private: synthetic\n')
        self.assertEqual(check_repository(self.root), [])
        subprocess.run(['git', '-C', str(self.root), 'add', '-f', 'private/house.yaml'], check=True)
        self.assertTrue(any('private/' in error for error in check_repository(self.root)))

    def test_new_nested_environment_and_plan_images_are_rejected(self):
        for path in ['docs/.env.local', 'docs/house.png', 'docs/plan.PDF']:
            self.write(path, 'synthetic')
        self.write('.env.example', 'BROKER=mqtt.example\n')
        self.write('tests/fixtures/synthetic.png', 'synthetic')
        errors = check_repository(self.root)
        self.assertEqual(len(errors), 3)

    def test_missing_file_and_constitution_section_are_rejected(self):
        (self.root / 'specs/001-test/tasks.md').unlink()
        self.write('specs/001-test/plan.md', '# A plan\n')
        errors = check_repository(self.root)
        self.assertTrue(any('tasks.md' in error for error in errors))
        self.assertTrue(any('Constitution Check' in error for error in errors))

    def test_instruction_and_constitution_files_are_required(self):
        (self.root / 'AGENTS.md').unlink()
        (self.root / '.specify/memory/constitution.md').unlink()
        self.assertEqual(len(check_repository(self.root)), 2)

    def test_ssid_examples_require_explicit_fictional_prefix(self):
        for key in ['ssid', 'wifi-ssid', 'home_ssid']:
            with self.subTest(key=key):
                self.write('examples/wifi.yaml', key + ': household-wifi\n')
                self.assertEqual(len(check_repository(self.root)), 1)
                self.write('examples/wifi.yaml', key + ': example-wifi\n')
                self.assertEqual(check_repository(self.root), [])

    def test_requirement_mentions_outside_tasks_do_not_count(self):
        self.write('specs/001-test/tasks.md', 'FR-001\n- [ ] T001 Implement FR-0010.\n')
        errors = check_repository(self.root)
        self.assertTrue(any('no checkbox task' in error for error in errors))
        self.assertTrue(any('unknown requirement' in error for error in errors))

    def test_duplicate_declarations_and_unknown_plan_references_rejected(self):
        self.write('specs/001-test/spec.md', '- **FR-001**: One.\n- **FR-001**: Two.\n')
        self.write('specs/001-test/plan.md', '## Constitution Check\nFR-999\n')
        errors = check_repository(self.root)
        self.assertTrue(any('duplicate' in error for error in errors))
        self.assertTrue(any('unknown requirement' in error for error in errors))

    def test_real_network_identifiers_in_examples_rejected_without_echoing_values(self):
        self.write('examples/nodes.example.yaml', 'site: real-house\nbroker:\n  host: 192.168.4.9\nnodes:\n- mac: AA:BB:CC:DD:EE:FF\n  address: home-router\n')
        errors = check_repository(self.root)
        self.assertEqual(len(errors), 4)
        self.assertNotIn('192.168.4.9', '\n'.join(errors))

    def test_malformed_yaml_is_reported_without_echoing_content(self):
        self.write('examples/bad.yaml', 'secret: [malformed\n')
        self.assertEqual(check_repository(self.root), ['examples/bad.yaml: invalid YAML'])

    def test_missing_requested_scanner_fails_closed(self):
        script = Path(__file__).resolve().parents[1] / 'tooling/governance/check_repository.py'
        result = subprocess.run([
            sys.executable, str(script), '--root', str(self.root),
            '--gitleaks', str(self.root / 'does-not-exist'),
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Unable to run Gitleaks', result.stderr)
        self.assertNotIn('Traceback', result.stderr)


# CI runs this integration check after installing the pinned scanner. Ordinary
# unit discovery does not require network access or install external executables.
if os.environ.get('GITLEAKS_EXECUTABLE'):
    class GitleaksIntegrationTests(unittest.TestCase):
        def test_synthetic_irk_is_detected_and_redacted(self):
            config = Path(__file__).resolve().parents[1] / '.gitleaks.toml'
            with tempfile.TemporaryDirectory() as directory:
                synthetic = secrets.token_hex(16)
                Path(directory, 'device.yaml').write_text('irk: ' + synthetic, encoding='utf-8')
                result = subprocess.run([
                    os.environ['GITLEAKS_EXECUTABLE'], 'dir', directory,
                    '--config', str(config), '--redact=100', '--no-banner',
                ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, 'Synthetic IRK must trigger the scanner')
            self.assertNotIn(synthetic, result.stdout + result.stderr)

        def test_working_file_scan_ignores_local_dependencies_but_catches_forced_files(self):
            config = Path(__file__).resolve().parents[1] / '.gitleaks.toml'
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                subprocess.run(['git', 'init', '-q', directory], check=True)
                (root / '.gitleaks.toml').write_bytes(config.read_bytes())
                (root / '.gitignore').write_text('dependencies/\n', encoding='utf-8')
                (root / 'dependencies').mkdir()
                (root / 'dependencies/device.yaml').write_text('irk: ' + secrets.token_hex(16), encoding='utf-8')
                executable = os.environ['GITLEAKS_EXECUTABLE']
                self.assertEqual(scan_working_files(root, executable), 0)
                subprocess.run(['git', '-C', directory, 'add', '-f', 'dependencies/device.yaml'], check=True)
                self.assertEqual(scan_working_files(root, executable), 1)


if __name__ == '__main__':
    unittest.main()
