"""Ordered runtime, durable-before-output transitions, and explicit degraded health."""
import asyncio
import copy
import logging
from time import monotonic, time as wall_time

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.helpers.storage import Store
import voluptuous as vol

from .config import validate_config
from .engine import Engine
from .runtime_io import subscribe
from .runtime_store import envelope, restore, storage_expected

DOMAIN = "espresense_pet"
QUEUE_LIMIT = 256
LOGGER = logging.getLogger(__name__)


class Coordinator:
    def __init__(self, hass, config, *, clock=None, wall=None):
        self.hass = hass
        self.config = validate_config(config)
        self.clock, self.wall = clock or monotonic, wall or wall_time
        self.engine = Engine(self.config)
        self.camera_sources = {}
        self.store = Store(hass, 1, f'{DOMAIN}.{self.config["pet_id"]}', private=True, atomic_writes=True)
        self.storage_ok = True
        self.overflow = False
        self.processing_ok = True
        self.queue = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self.unsubscribers = []
        self.listeners = {}
        self.worker = None
        self.stopped = False
        self.desired_connected = None
        self.saved = None
        self.pending_incident = False
        self.pending_reason = None
        self.pending_health = False
        self.state = self.engine.snapshot(self.clock())

    async def async_start(self):
        try:
            expected = await self.hass.async_add_executor_job(storage_expected, self.store.path)
            stored = await self.store.async_load()
            if stored is None and expected:
                raise ValueError("Prior incident storage is unreadable; operator restoration is required")
            self.engine, self.camera_sources = restore(self.config, stored)
            self.saved = stored
        except Exception:
            LOGGER.error("Private incident state could not be restored; setup stopped")
            return False
        self.worker = self.hass.async_create_background_task(self._run(), "Pet advisory evidence queue")
        try:
            if not await subscribe(self):
                await self.async_stop()
                return False
        except Exception:
            LOGGER.error("Pet evidence subscriptions could not be initialized")
            await self.async_stop()
            return False

        async def acknowledge(_call):
            self.enqueue("acknowledge", (), self.clock())
            await self.async_flush()

        self.hass.services.async_register(DOMAIN, "acknowledge", acknowledge, schema=vol.Schema({}))
        self.unsubscribers.append(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._shutdown))
        await self.async_flush()
        return True

    @callback
    def transport_status(self, connected):
        if self.stopped or connected == self.desired_connected:
            return
        self.desired_connected = connected
        self.enqueue("transport", (connected,), self.clock())

    @callback
    def enqueue(self, method, args, now):
        if self.stopped:
            return
        if self.queue.full():
            self.overflow = True
            while not self.queue.empty():
                self.queue.get_nowait()
                self.queue.task_done()
            # Missing events cannot be treated as continuous positive evidence.
            self.queue.put_nowait(("reset", (), now))
            return
        self.queue.put_nowait((method, args, now))

    async def _run(self):
        while True:
            method, args, now = await self.queue.get()
            try:
                await self._process(method, args, now)
            except Exception:
                self.processing_ok = False
                self.engine.transport(False, max(now, self.engine._now))
                LOGGER.error("Pet evidence processing failed; positive evidence invalidated")
                self._publish(max(now, self.engine._now))
            finally:
                self.queue.task_done()

    def _rollback(self, previous, sources, now):
        self.engine = Engine(self.config, restored=previous)
        self.camera_sources = sources
        if self.desired_connected:
            self.engine.transport(True, now)

    async def _process(self, method, args, now):
        previous = self.engine.dump()
        previous_sources = copy.deepcopy(self.camera_sources)
        fresh = self.config["timing"]["observation_fresh_s"]
        if method == "reset" or method == "observe" and self.clock() - now > fresh:
            self.engine.transport(False, now)
            intents = self.engine.transport(bool(self.desired_connected), now)
        elif method == "camera" and self.clock() - args[3] > fresh:
            intents = self.engine.advance(now)
        else:
            intents = getattr(self.engine, method)(*args, now)
        if method == "camera" and any(item["reason"] in ("camera_inside", "camera_outside") for item in intents):
            door, _zone, event_id, _evidence = args
            self.camera_sources[door] = {"camera": self.config["doors"][door]["camera"], "event_id": event_id}
        recovering = previous["alert"]["level"] != "clear" and self.engine.alert["level"] == "clear"
        if recovering and not self.storage_ok:
            self._rollback(previous, previous_sources, now)
            intents = [item for item in intents if item["level"] != "recovered"]
            recovering = False
        if self.engine.alert["level"] == "clear":
            self.camera_sources = {}
        for item in intents:
            if item["level"] in ("suspected", "urgent"):
                self.pending_incident = True
                self.pending_reason = item["reason"]
            self.pending_health |= item["level"] == "health"
        data = envelope(self.engine, self.camera_sources)
        try:
            if data != self.saved or not self.storage_ok:
                await self.store.async_save(data)
                self.saved = data
            self.storage_ok = True
        except Exception:
            self.storage_ok = False
            if recovering:
                self._rollback(previous, previous_sources, now)
            self._publish(now)
            return
        self._publish(now)
        if self.pending_incident and self.engine.alert["level"] != "clear":
            self._emit({"level": self.engine.alert["level"], "door": self.engine.alert["door"], "reason": self.pending_reason})
        self.pending_incident = False
        self.pending_reason = None
        if self.pending_health and self.state["health"] == "device_silence":
            self._emit({"level": "health", "door": None, "reason": "device_silence"})
        self.pending_health = False
        for item in intents:
            if item["level"] == "recovered" or item["level"] == "heads_up" and self.clock() - now <= fresh:
                self._emit(item)

    @callback
    def _emit(self, item):
        data = {"pet_id": self.config["pet_id"], **item}
        if item["level"] in ("suspected", "urgent") and item["door"] in self.camera_sources:
            data["camera_reference"] = dict(self.camera_sources[item["door"]])
        self.hass.bus.async_fire("espresense_pet_advisory", data)

    @callback
    def _publish(self, now):
        # Receipt time orders the engine; publication time determines whether
        # evidence is still fresh after queueing and asynchronous disk writes.
        self.state = self.engine.snapshot(max(now, self.clock()))
        for listener, _priority in sorted(self.listeners.items(), key=lambda item: item[1]):
            listener()

    @callback
    def listen(self, listener, *, priority=0):
        self.listeners[listener] = priority
        return lambda: self.listeners.pop(listener, None)

    async def async_flush(self):
        await self.queue.join()

    async def _shutdown(self, _event):
        await self.async_stop()

    async def async_stop(self):
        if self.stopped:
            return
        self.stopped = True
        for unsubscribe in reversed(self.unsubscribers):
            unsubscribe()
        self.unsubscribers.clear()
        self.hass.services.async_remove(DOMAIN, "acknowledge")
        if self.worker is not None:
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
        self.listeners.clear()
