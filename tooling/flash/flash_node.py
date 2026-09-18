"""Flash ESPresense onto a node from the pinned images in firmware.lock.

    python tooling/flash/flash_node.py --port COM6 [--target atoms3-lite] [--watch]

Downloads each part once into ~/.cache/espresense-fleet/, verifies sha256, writes all parts in
one esptool invocation, then (with --watch) resets the board and prints its boot log until the
setup-AP line appears.
"""
import argparse
import hashlib
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

import yaml

HERE = pathlib.Path(__file__).resolve().parent
CACHE = pathlib.Path.home() / ".cache" / "espresense-fleet"
AP_LINE = re.compile(r"SSID: '(espresense-[0-9a-f]{6})'")


def fetch(url: str, sha256: str) -> pathlib.Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / sha256[:16] / url.rsplit("/", 1)[-1]
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"  downloading {url}")
        urllib.request.urlretrieve(url, dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    if digest != sha256:
        dest.unlink()
        sys.exit(f"checksum mismatch for {url}: got {digest}, expected {sha256}")
    return dest


def watch(port: str, seconds: int) -> str | None:
    import serial  # pyserial, pulled in by esptool

    s = serial.Serial()
    s.port, s.baudrate, s.timeout = port, 115200, 1
    s.dtr = False
    s.rts = False
    s.open()
    s.rts = True
    time.sleep(0.1)
    s.rts = False
    buf, end = b"", time.time() + seconds
    while time.time() < end:
        chunk = s.read(4096)
        if chunk:
            buf += chunk
            m = AP_LINE.search(buf.decode(errors="replace"))
            if m:
                s.close()
                return m.group(1)
    s.close()
    print(buf.decode(errors="replace")[-1500:])
    return None


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="serial port, e.g. COM6 or /dev/ttyACM0")
    ap.add_argument("--target", default="atoms3-lite")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--watch", action="store_true", help="after flashing, print the boot log until the setup AP appears")
    ap.add_argument("--download-only", action="store_true", help="verify all pinned downloads without opening a serial port")
    args = ap.parse_args(argv)
    if args.baud <= 0:
        ap.error("--baud must be positive")
    if not args.download_only and not args.port:
        ap.error("--port is required unless --download-only is used")
    if args.download_only and args.watch:
        ap.error("--watch cannot be used with --download-only")

    lock = yaml.safe_load((HERE / "firmware.lock").read_text())
    target = lock["targets"].get(args.target)
    if not target:
        sys.exit(f"unknown target {args.target!r}; known: {', '.join(lock['targets'])}")

    action = "verifying downloads for" if args.download_only else "flashing"
    print(f"{action} {args.target} (ESPresense {target['espresense_version']})")
    write_args: list[str] = []
    for part in target["parts"]:
        path = fetch(part["url"], part["sha256"])
        write_args += [part["offset"], str(path)]
        print(f"  {part['name']:<11} @ {part['offset']:<8} {path.name}")

    if args.download_only:
        print("DONE: all four pinned firmware checksums verified; no serial port opened.")
        return

    cmd = [sys.executable, "-m", "esptool", "--chip", target["chip"], "--port", args.port,
           "--baud", str(args.baud), "--after", "hard_reset", "write_flash", *write_args]
    print("  " + " ".join(cmd[1:]))
    subprocess.run(cmd, check=True)
    print("flash complete; board reset")

    if args.watch:
        print("waiting for the setup access point ...")
        ssid = watch(args.port, 20)
        if ssid:
            print(f"DONE: node is broadcasting {ssid} (label the board with it). Unplug it from this PC when you're finished.")
        else:
            sys.exit("no setup-AP line seen within 20 s; see the boot log above")


if __name__ == "__main__":
    main()
