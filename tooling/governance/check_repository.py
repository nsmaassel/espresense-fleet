"""Check narrow public-repository policies; this is not semantic/privacy review.

Checks tracked files (even force-added ignored files) and nonignored new files.
Example network identifiers must be fictional. Prose, geometry, image contents,
requirement coverage quality and constitutional compliance still need review.
Run Gitleaks separately for secrets, including git history.
"""
import argparse
from collections import Counter
import ipaddress
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile

import yaml


REQUIREMENT = re.compile(r'\bFR-\d+\b')
DECLARATION = re.compile(r'^\s*-\s+\*\*(FR-\d{3})\*\*:', re.MULTILINE)
TASK = re.compile(r'^\s*-\s+\[[ xX]\]\s+.*$', re.MULTILINE)
DOCUMENTATION_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    '192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24', '2001:db8::/32',
))
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.pdf', '.bmp', '.tif', '.tiff'}


def repository_files(root):
    result = subprocess.run(
        ['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
        check=True, capture_output=True,
    )
    return sorted(set(result.stdout.decode('utf-8').split('\0')) - {''})


def fictional_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        value = str(value).lower().rstrip('.')
        return value == 'localhost' or any(
            value == domain or value.endswith('.' + domain)
            for domain in ('example', 'test', 'invalid', 'example.com', 'example.org', 'example.net')
        )
    return any(address.version == network.version and address in network
               for network in DOCUMENTATION_NETWORKS)


def check_example(value, path, errors):
    if isinstance(value, list):
        for child in value:
            check_example(child, path, errors)
    elif isinstance(value, dict):
        for key, child in value.items():
            key = str(key).lower()
            if child is not None:
                if key in {'host', 'address', 'ip', 'hostname'} and not fictional_address(child):
                    errors.append(f'{path}: example {key} must use a documentation address/domain')
                if key == 'mac' and not re.fullmatch(r'02:00:00:00:00:[0-9a-fA-F]{2}', str(child)):
                    errors.append(f'{path}: example mac must be null or 02:00:00:00:00:xx')
                if key == 'site' and not str(child).startswith('example-'):
                    errors.append(f'{path}: example site must start with example-')
                if key in {'ssid', 'wifi-ssid', 'home_ssid', 'wifi_ssid'} and not str(child).startswith('example-'):
                    errors.append(f'{path}: example SSID must start with example-')
            check_example(child, path, errors)


def check_specs(root, files, errors):
    features = sorted({PurePosixPath(path).parts[1] for path in files
                       if path.startswith('specs/') and len(PurePosixPath(path).parts) >= 3})
    for feature in features:
        base = f'specs/{feature}'
        documents = {}
        for name in ('spec.md', 'plan.md', 'tasks.md'):
            path = f'{base}/{name}'
            if path not in files or not (root / path).is_file():
                errors.append(f'{path}: required spec artifact missing')
            else:
                documents[name] = (root / path).read_text(encoding='utf-8')
        if 'plan.md' in documents and not re.search(r'^## Constitution Check\s*$', documents['plan.md'], re.MULTILINE):
            errors.append(f'{base}/plan.md: missing ## Constitution Check')
        if 'spec.md' not in documents:
            continue
        counts = Counter(DECLARATION.findall(documents['spec.md']))
        if not counts:
            errors.append(f'{base}/spec.md: declare requirements as - **FR-001**: ...')
        for requirement, count in counts.items():
            if count > 1:
                errors.append(f'{base}/spec.md: duplicate requirement {requirement}')
        for name, content in documents.items():
            for requirement in sorted(set(REQUIREMENT.findall(content)) - counts.keys()):
                errors.append(f'{base}/{name}: unknown requirement {requirement}')
        if 'tasks.md' in documents:
            task_ids = set(REQUIREMENT.findall('\n'.join(TASK.findall(documents['tasks.md']))))
            for requirement in sorted(counts.keys() - task_ids):
                errors.append(f'{base}/tasks.md: no checkbox task references {requirement}')


def check_repository(root):
    root = Path(root).resolve()
    files = repository_files(root)
    errors = []
    for required in ('AGENTS.md', '.specify/memory/constitution.md'):
        if required not in files or not (root / required).is_file():
            errors.append(f'{required}: required governance file missing')
    for name in files:
        path = PurePosixPath(name)
        lower_parts = [part.lower() for part in path.parts]
        basename = path.name.lower()
        if 'private' in lower_parts or (basename != '.env.example' and
                                        (basename == '.env' or basename.startswith('.env.'))):
            errors.append(f'{name}: private path is prohibited in the public repository')
        if path.suffix.lower() in IMAGE_SUFFIXES and not name.startswith('tests/fixtures/'):
            errors.append(f'{name}: images/plans belong outside git; only synthetic tests/fixtures/ assets allowed')
        disk_path = root / name
        if disk_path.is_symlink():
            errors.append(f'{name}: symlinks cannot be checked for public content')
            continue
        if name.startswith('examples/') and path.suffix.lower() in {'.yaml', '.yml'} and disk_path.is_file():
            try:
                value = yaml.safe_load(disk_path.read_text(encoding='utf-8'))
            except (yaml.YAMLError, UnicodeError):
                errors.append(f'{name}: invalid YAML')
            else:
                check_example(value, name, errors)
    check_specs(root, [name for name in files if not (root / name).is_symlink()], errors)
    return errors


def scan_working_files(root, executable):
    """Scan publishable files, without ignored local dependencies or secrets."""
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix='espresense-public-scan-') as directory:
        destination = Path(directory)
        for name in repository_files(root):
            source = root / name
            if source.is_file() and not source.is_symlink():
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        result = subprocess.run([
            executable, 'dir', str(destination), '--config', str(root / '.gitleaks.toml'),
            '--redact=100', '--no-banner',
        ], check=False)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--gitleaks', metavar='EXECUTABLE', help='also scan publishable working files for secrets (history scanned separately in CI)')
    args = parser.parse_args()
    try:
        errors = check_repository(args.root)
    except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
        parser.exit(2, f'Unable to check repository ({type(error).__name__}).\n')
    for error in errors:
        print(error)
    if not errors:
        print('Repository policy checks passed. Semantic and privacy review still required.')
        if args.gitleaks:
            try:
                return scan_working_files(args.root, args.gitleaks)
            except (OSError, subprocess.CalledProcessError) as error:
                parser.exit(2, f'Unable to run Gitleaks ({type(error).__name__}).\n')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
