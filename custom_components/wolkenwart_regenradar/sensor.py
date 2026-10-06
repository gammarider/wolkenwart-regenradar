"""Forecast, plan and data quality sensors."""

from datetime import timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from .entity import RadarEntity

KEYS = (
    "rain_start",
    "close_at",
    "peak_next_hour",
    "precipitation_next_hour",
    "source_time",
    "data_age",
    "data_status",
)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(RadarSensor(entry.runtime_data, key) for key in KEYS)


class RadarSensor(RadarEntity, SensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        if key in ("rain_start", "close_at", "source_time"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        if key == "peak_next_hour":
            self._attr_device_class = SensorDeviceClass.PRECIPITATION_INTENSITY
            self._attr_native_unit_of_measurement = "mm/h"
        elif key == "precipitation_next_hour":
            self._attr_device_class = SensorDeviceClass.PRECIPITATION
            self._attr_native_unit_of_measurement = "mm"
        elif key == "data_age":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = "s"
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key == "data_status":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = ["current", "cached", "expired", "no_data"]
        if key in ("source_time", "data_age", "data_status"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self):
        if self.key in ("source_time", "data_age", "data_status"):
            return True
        return super().available

    @property
    def native_value(self):
        c = self.coordinator
        view = c.view()
        if self.key == "data_status":
            return view["status"]
        if self.key == "data_age":
            age = view["source_age_seconds"]
            return round(age) if age is not None else None
        if self.key == "source_time":
            return view["source_time"]
        if not c.usable:
            return None
        now = dt_util.utcnow()
        if self.key in ("rain_start", "close_at"):
            at = c.forecast.rain_start(now, c.threshold)
            return (
                at - timedelta(minutes=c.lead) if at and self.key == "close_at" else at
            )
        amount, peak = c.forecast.next_hour(now)
        return peak if self.key == "peak_next_hour" else amount
