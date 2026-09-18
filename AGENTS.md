# AGENTS.md — operating espresense-fleet for a human

You are setting up BLE room presence in someone's home. The person does the physical
steps (plugging boards in, walking around, typing their Wi-Fi password); you do
everything else. Read [`docs/runbook.md`](docs/runbook.md) once before the first node.

## Hard rules

1. **Never handle the Wi-Fi password.** `Setup-ESPresenseNode.ps1` prompts for it locally
   in the human's terminal. Do not ask for it in chat, do not put it in a file.
2. **Never commit private config to this repo.** MACs, IPs, SSIDs and room polygons of a real
   house go to the human's private repo or `private/` (git-ignored). Passwords and `irk:`
   enrollment keys stay outside every git repository, in a secret store. Treat an IRK
   as a tracking credential.
3. **A provisioned node must not stay plugged into a PC.** The host's serial driver can park
   an ESP32-S3 in ROM download mode on plug-in (USB enumerates, no LED, no boot), and opening
   the serial port resets a running node. Provision on the PC, then move it to a wall adapter.
   Check running nodes over the LAN (`GET http://<ip>/wifi/main`), not over serial.
4. **Ask before anything visible to others** (creating repos, posting issues, publishing).

## The flow

Work through these in order; each step's "done" check is what you report back.

| # | Step | Tool | Done when |
|---|---|---|---|
| 1 | Inventory | ask: boards, broker host:port (anonymous?), HA present?, plan images? | `nodes.yaml` skeleton exists with one row per board |
| 2 | Flash | `python tooling/flash/flash_node.py --port <COM/tty>` | serial boot log shows `Starting access point … SSID: 'espresense-xxxxxx'` |
| 3 | Provision | `pwsh tooling/provision/Setup-ESPresenseNode.ps1 -ApSsid … -RoomName … -HomeSsid … -MqttHost … -MqttPort …` (human runs it — it prompts for the password) | status topic → `online` plus fresh telemetry from that node |
| 4 | Hardware | `python tooling/provision/espresense_set.py <ip> hardware led_1_type=2 led_1_pin=35 led_1_cnt=1 led_1_cntrl=1` (AtomS3 Lite) | LED white = Wi-Fi + MQTT |
| 5 | Layout | `docs/layout.md`: plan images → `geometry.yaml` → `python tooling/layout/build_layout_page.py geometry.yaml` → human drags dots → paste YAML | `nodes:` block with a point for every node |
| 6 | Enroll a phone | `mosquitto_pub -t espresense/rooms/<room>/enroll/set -m 'example-phone|Example Phone'`, human pairs from the phone's Bluetooth settings | `espresense/settings/irk:…/config` published; restart nodes that already cached the phone under an `apple:` id |
| 7 | Calibration walk | record `espresense/devices/<id>/+` while the human walks room→room→room, 20 s per stop; bucket into 5–10 s windows; report which node "won" each window | clean flip at each transition, no flips while stationary; note any node that never hears the device closer than ~3 m |
| 8 | Hand off | write the private config: `nodes.yaml`, `companion/config.yaml` (floors + nodes), broker details; summarize gotchas hit | human can rerun every step from the private repo alone |

## Facts you will otherwise rediscover the hard way

- The GitHub release `.bin` (e.g. `esp32s3-cdc.bin`) is the **app partition only**. Flashing it
  alone at `0x0` gives a silent board. `flash_node.py` writes bootloader `0x0`, partitions
  `0x8000`, `boot_app0` `0xe000`, app `0x10000`, all pinned in `tooling/flash/firmware.lock`.
- AtomS3 Lite uses the ESP32-S3's native USB-CDC → use the `-cdc` firmware variant.
- Provisioning is `POST /wifi/main`, `application/x-www-form-urlencoded`, fields `room`,
  `wifi-ssid`, `wifi-password`, `mqtt_host`, `mqtt_port`, … A **missing key** means "empty";
  a checkbox is on only if its key is present — sending the string `False` turns it **on**.
  The API returns stored passwords as `***###***` and keeps the stored value when that
  placeholder is sent back, so later changes over the LAN need no password.
- Generic ESP32-S3 builds default LED 1 to PWM on GPIO 2. AtomS3 Lite's LED is a WS2812 on
  GPIO 35 (`led_1_type=2`, `led_1_pin=35`, `led_1_cnt=1`).
- Status LED: red = joining Wi-Fi · pink = setup portal (Wi-Fi failed after 60 s; retries after
  300 s) · yellow = Wi-Fi ok, no MQTT · white = both ok · green = updating.
- Keep nodes **≥ 2 m from Wi-Fi routers/APs** — a node beside the router had −32 dBm Wi-Fi
  and never heard a phone closer than 5 m.
- iPhones cannot be a stand-in beacon via nRF Connect (no iBeacon, name stripped, stops in
  background). Enroll them instead (step 6). Android can advertise a real iBeacon.
- Enrollment keys are **retained MQTT messages on that broker**. Moving to another broker means
  re-enrolling or republishing `espresense/settings/irk:<key>/config`.
- Windows `netsh wlan show networks` is a stale cache; a node's setup AP can look present for
  minutes after it has joined Wi-Fi.
- ESPresense Companion estimates a position from several nodes. The upstream placement guide
  recommends aiming for at least five fixes; validate signal overlap in each zone. Room and
  coordinate accuracy depend on calibration, with no fixed error bound established here.
  See https://espresense.com/companion/configuration/#node-placement.

## Where things are

- Spec Kit: `.specify/memory/constitution.md` (principles), `specs/` (features). Follow the
  constitution when adding scope; propose a spec before building a stage that doesn't exist.
- The reference run this repo was written from: nine AtomS3 Lites, two floors, Home
  Assistant on a separate host, broker on the LAN. If your user's setup differs, say so
  early and adapt the flow rather than forcing it.
