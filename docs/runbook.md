# Runbook — flash, provision, enroll, verify

Written from a real run on 2026-09-17 (AtomS3 Lite, Windows 11 host, Mosquitto on the LAN).
Commands assume the repo root as the working directory.

## 0. Before you start

- Python 3.11+ with `esptool` (`python -m pip install -r requirements.txt`).
- PowerShell 7 (`pwsh`) on Windows for the provisioning script.
- Mosquitto clients (`mosquitto_sub`, `mosquitto_pub`) on the broker host or operator machine.
- An existing saved home Wi-Fi profile on the Windows PC. Its name defaults to `HomeSsid`;
  pass `-HomeProfile "Profile name"` if Windows saved it under another name.
- A **data** USB-C cable. A charge-only cable is the single most common "nothing shows up".
  A lit LED proves power, not a working USB data connection.
- An MQTT broker reachable from the Wi-Fi the nodes will join. Anonymous is fine for a start.
- One node at a time on the PC. Boards left plugged into a PC after provisioning get parked in
  ROM download mode by the host's serial driver (USB enumerates, no LED, no boot). Provision,
  then move to a wall adapter.

## 1. Flash

```
python tooling/flash/flash_node.py --port COM6            # Windows
python tooling/flash/flash_node.py --port /dev/ttyACM0    # Linux/macOS
```

What it does: downloads the four images pinned in `tooling/flash/firmware.lock` (verifying
sha256), then writes bootloader `0x0`, partitions `0x8000`, `boot_app0` `0xe000`, app `0x10000`.
The GitHub release `.bin` alone is only the app partition — flashing just that gives a silent board.

**Done when:** the boot log shows `Starting access point for configuration portal. SSID: 'espresense-xxxxxx'`.
`flash_node.py --port COM6 --watch` prints it. Record the observed SSID and hardware MAC separately; do not infer the MAC
from the AP suffix. Add a stable physical label such as `node01` **now**.

## 2. Provision (first time, over the node's own Wi-Fi)

Windows (the script joins the AP, prompts for the password locally, saves, restarts, rejoins your Wi-Fi):

```
pwsh -ExecutionPolicy Bypass -File tooling/provision/Setup-ESPresenseNode.ps1 `
  -ApSsid espresense-xxxxxx -RoomName kitchen -HomeSsid <your ssid> -MqttHost 192.0.2.20 -MqttPort 1883
```

Linux/macOS: join `espresense-xxxxxx` manually, then `python tooling/provision/espresense_set.py 192.168.4.1 main room=kitchen wifi-ssid=<ssid> wifi-password=- mqtt_host=192.0.2.20 mqtt_port=1883`
(`wifi-password=-` prompts). Rejoin your Wi-Fi afterwards.

Under the hood: `POST /wifi/main`, form-urlencoded. The tool first `GET`s the current config so
nothing else is clobbered; checkbox fields are sent only when true (the firmware treats any
non-empty value — including the string `False` — as on).

**Done when:** the status topic reports `online` and fresh telemetry arrives. A retained
`online` message alone can be stale. Use a bounded subscription while checking the node:
`mosquitto_sub -h <broker> -v -t 'espresense/rooms/kitchen/status' -t 'espresense/rooms/kitchen/telemetry' -W 30`.
Find the node's IP with `ip neigh | grep -i <mac>` or your router.

## 3. Hardware settings (AtomS3 Lite)

The generic ESP32-S3 build drives a PWM LED on GPIO 2; the AtomS3 Lite has a WS2812 on GPIO 35.

```
python tooling/provision/espresense_set.py <node-ip> hardware led_1_type=2 led_1_pin=35 led_1_cnt=1 led_1_cntrl=1
```

LED meaning afterwards: **red** joining Wi-Fi · **pink** setup portal (Wi-Fi failed after 60 s;
retries after 300 s) · **yellow** Wi-Fi ok, no MQTT · **white** Wi-Fi + MQTT · **green** updating.
`led_1_cntrl=0` makes it an MQTT light instead (`espresense/rooms/<room>/led_1/set`).

## 4. Change anything later, over the LAN, no password

```
python tooling/provision/espresense_set.py <node-ip> main room=office mqtt_port=1883
```

The API returns stored passwords as `***###***` and keeps the stored value when that
placeholder is sent back. Endpoints: `main` (room, Wi-Fi, MQTT, updates), `hardware` (LEDs,
sensors), `extras`. `GET http://<ip>/wifi/<endpoint>` shows `values` and `defaults`.

## 5. Enroll a phone (stable id despite address rotation)

```
mosquitto_pub -h <broker> -t 'espresense/rooms/kitchen/enroll/set' -m 'example-phone|Example Phone'
```

Within 120 s, on the phone: Settings → Bluetooth → pair with the new `ESPresense-…` device.
The node reads the phone's IRK, publishes a retained `espresense/settings/irk:<key>/config`
with your id, and every node on that broker resolves the phone from then on — screen off,
no app. Restart any node that had already cached the phone under an `apple:` fingerprint.

The key is a retained message **on that broker**. New broker → re-enroll or republish it.
Treat it as a credential.

## 6. Verify

```
mosquitto_sub -h <broker> -v -t 'espresense/devices/example-phone/+'
```

Walk between two nodes; the shorter `distance` should follow you. Then read `docs/layout.md`.

## Gotchas, in the order we hit them

| Symptom | Cause | Fix |
|---|---|---|
| Board invisible to the OS, LED lights up | charge-only cable | data cable |
| Flashed, no AP, silent serial | app-only `.bin` at 0x0 | `flash_node.py` (all four images) |
| Windows still lists `espresense-xxxxxx` after provisioning | `netsh` scan cache | check `online` status plus fresh node telemetry |
| Node reboots every time you look at serial | opening the USB-CDC port resets the ESP32-S3 (`rst:0x15`) | stop looking; use the LAN |
| Node solid red forever after a few resets | Wi-Fi radio wedged | power-cycle from a wall adapter |
| USB enumerates, no LED at all, nothing on serial | host driver parked it in download mode on plug-in | `python -m esptool --chip esp32s3 --port COMx --after hard_reset chip_id`, then unplug from the PC |
| LED never comes on after Wi-Fi joins | LED type/pin defaults wrong for the board | step 3 |
| Node beside the router hears nothing closer than 5 m | 2.4 GHz desense | move node ≥ 2 m from any AP |
| Pink LED at a far spot | 60 s Wi-Fi timeout | better spot or better Wi-Fi; check RSSI in `espresense/rooms/<room>/telemetry` |
| iPhone + nRF Connect not visible / changes id | iOS strips the name, no iBeacon, stops in background | enroll (step 5) |
| Phone enrolled but one node still shows `apple:…` | cached fingerprint | restart that node |

## Calibration walk

Use an enrolled phone and pause for 20 seconds at each stop: room A, room B, room A.
Capture only that device topic, including timestamps, and compare winners in 5–10 second
windows. Record the expected stop times and any false flips while stationary. A short
walk verifies this route only; repeat with the actual collar beacon, closed doors and
normal furniture before relying on household coverage. Lost BLE reception alone is
not evidence that a pet is outside.
