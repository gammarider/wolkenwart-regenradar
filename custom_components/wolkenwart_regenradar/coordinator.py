"""Acquisition, retries and independent wall-clock expiry."""

import asyncio
import hashlib
import logging
from datetime import timedelta

import aiohttp
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DEFAULT_LEAD, DEFAULT_MAX_AGE, DEFAULT_THRESHOLD, NAME
from .core import data_status, target_release
from .radar import RadarError, decode_archive, download

_LOGGER = logging.getLogger(__name__)


class RadarCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=NAME,
            update_interval=timedelta(seconds=30),
        )
        self.entry = entry
        self.forecast = None
        self.last_error = None
        self.last_attempt = None
        self.next_attempt = dt_util.utcnow()
        self.offset = (
            int.from_bytes(hashlib.sha256(entry.entry_id.encode()).digest()[:4], "big")
            % 31
        )
        self._timers = []
        self._stopped = False

    @property
    def max_age(self):
        return self.entry.options.get("max_age", DEFAULT_MAX_AGE)

    @property
    def threshold(self):
        return self.entry.options.get("threshold", DEFAULT_THRESHOLD)

    @property
    def lead(self):
        return self.entry.options.get("lead_minutes", DEFAULT_LEAD)

    @property
    def usable(self):
        return self.forecast is not None and self.forecast.valid(
            dt_util.utcnow(), self.max_age
        )

    def view(self):
        now = dt_util.utcnow()
        forecast = self.forecast
        return {
            "status": data_status(forecast, now, self.max_age, self.offset),
            "source_time": forecast.release if forecast else None,
            "source_age_seconds": (now - forecast.start).total_seconds()
            if forecast
            else None,
            "valid_until": forecast.deadline(self.max_age) if forecast else None,
            "last_attempt": self.last_attempt,
            "last_error": self.last_error,
        }

    def _arm_timers(self):
        for cancel in self._timers:
            cancel()
        self._timers.clear()
        now = dt_util.utcnow()
        if not self.forecast or self._stopped:
            return
        targets = {self.forecast.deadline(self.max_age)}
        rain = self.forecast.rain_start(now, self.threshold)
        if rain:
            targets.add(rain - timedelta(minutes=self.lead))
        for at in targets:
            if at > now:
                self._timers.append(
                    async_track_point_in_utc_time(self.hass, self._clock_changed, at)
                )

    @callback
    def _clock_changed(self, _now):
        if not self._stopped:
            self.async_update_listeners()

    async def _async_update_data(self):
        now = dt_util.utcnow()
        release = target_release(now, self.offset)
        if now >= self.next_attempt and (
            self.forecast is None or release > self.forecast.release
        ):
            self.last_attempt = now
            try:
                blob = await download(async_get_clientsession(self.hass), release)
                result = await self.hass.async_add_executor_job(
                    decode_archive,
                    blob,
                    release,
                    self.entry.data["latitude"],
                    self.entry.data["longitude"],
                )
                # Never make a late response or expired source usable again.
                if not result.valid(dt_util.utcnow(), self.max_age):
                    raise RadarError("Forecast expired during request")
                self.forecast = result
                self.last_error = None
                self.next_attempt = release + timedelta(seconds=300 + 250 + self.offset)
                self._arm_timers()
            except (
                RadarError,
                aiohttp.ClientError,
                asyncio.TimeoutError,
                ValueError,
            ) as err:
                self.last_error = str(err)
                self.next_attempt = dt_util.utcnow() + timedelta(seconds=60)
        return self.view()

    async def async_shutdown(self):
        self._stopped = True
        for cancel in self._timers:
            cancel()
        self._timers.clear()
        await super().async_shutdown()
