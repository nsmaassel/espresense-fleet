"""Hard process deadline also bounds DNS and third-party client shutdown."""
import multiprocessing
import os
from pathlib import Path

from .capture import capture
from .records import load_log


def bounded_process(target, args, timeout):
    process = multiprocessing.get_context("spawn").Process(target=target, args=args)
    process.start()
    try:
        process.join(timeout)
        if process.is_alive():
            raise ValueError("Capture exceeded its deadline; only incomplete partial evidence remains")
        if process.exitcode != 0:
            raise ValueError("Capture worker failed; inspect private partial evidence")
    finally:
        if process.is_alive():
            process.terminate()
            process.join(1)
        if process.is_alive():
            process.kill()
            process.join(1)
        if not process.is_alive():
            process.close()


def capture_worker(path, config, schedule, duration_ms, connect_timeout):
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, reconnect_on_failure=False)
        host = os.environ.get("ESPRESENSE_MQTT_HOST")
        if not host:
            raise ValueError("Broker environment variable missing")
        port = int(os.environ.get("ESPRESENSE_MQTT_PORT", "1883"))
        username = os.environ.get("ESPRESENSE_MQTT_USERNAME")
        password = os.environ.get("ESPRESENSE_MQTT_PASSWORD")
        if password and not username:
            raise ValueError("Username required with password")
        if username:
            client.username_pw_set(username, password)
        tls = os.environ.get("ESPRESENSE_MQTT_TLS", "0")
        if tls not in ("0", "1"):
            raise ValueError("Invalid TLS setting")
        if tls == "1":
            client.tls_set()
        with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
            capture(stream, config, schedule, duration_ms, client,
                    host=host, port=port, connect_timeout=connect_timeout,
                    on_started=lambda: print("Capture ready: elapsed time zero starts now. Follow the stop schedule.", flush=True))
    except BaseException:
        # Never let a traceback expose transport configuration or credentials.
        raise SystemExit(1) from None


def capture_file(output, config, schedule, duration_ms, connect_timeout=10):
    output = Path(output)
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        raise ValueError("Choose a new capture output; existing evidence is never overwritten")
    bounded_process(capture_worker, (str(partial), config, schedule, duration_ms, connect_timeout),
                    timeout=connect_timeout + duration_ms / 1000 + 2)
    log = load_log(partial)
    # Same-directory hard-link creation is atomic and fails if a competing writer
    # created the output during capture. Preserve both files on publication failure.
    os.link(partial, output)
    partial.unlink()
    return log["capture"]
