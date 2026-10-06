"""Read-only forecast and protection request; never motor control."""

from datetime import timedelta

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.util import dt as dt_util

from .entity import RadarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        RadarBinary(entry.runtime_data, key)
        for key in ("precipitation_expected", "protection_due")
    )


class RadarBinary(RadarEntity, BinarySensorEntity):
    _unrecorded_attributes = frozenset({"forecast_5min"})

    @property
    def is_on(self):
        c = self.coordinator
        if not c.usable:
            return None
        now = dt_util.utcnow()
        rain = c.forecast.rain_start(now, c.threshold)
        if self.key == "protection_due":
            return rain is not None and rain - timedelta(minutes=c.lead) <= now
        return rain is not None

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        if self.key == "precipitation_expected" and self.coordinator.usable:
            attrs["forecast_5min"] = self.coordinator.forecast.series()
        return attrs
