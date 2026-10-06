"""Entity identity is isolated from existing DWD integrations."""

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME, VERSION


class RadarEntity(CoordinatorEntity):
    _attr_has_entity_name = True
    _attr_attribution = "Datenquelle: Deutscher Wetterdienst (DWD)"

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": coordinator.entry.title,
            "manufacturer": "Wolkenwart",
            "model": NAME,
            "sw_version": VERSION,
        }

    @property
    def available(self):
        return self.coordinator.usable

    @property
    def extra_state_attributes(self):
        return self.coordinator.view()
