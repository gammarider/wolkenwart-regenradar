"""Location setup and conservative forecast options."""

import math

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DEFAULT_LEAD, DEFAULT_MAX_AGE, DEFAULT_THRESHOLD, DOMAIN, NAME
from .radar import RadarError, grid_cell


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self.hass.async_add_executor_job(
                    grid_cell, user_input["latitude"], user_input["longitude"]
                )
            except RadarError, ValueError, OverflowError:
                errors["base"] = "outside_coverage"
            else:
                await self.async_set_unique_id(
                    f"{user_input['latitude']:.5f},{user_input['longitude']:.5f}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input["name"], data=user_input
                )
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=NAME): str,
                    vol.Required(
                        "latitude", default=self.hass.config.latitude
                    ): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
                    vol.Required(
                        "longitude", default=self.hass.config.longitude
                    ): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            if not math.isfinite(user_input["threshold"]):
                return self.async_abort(reason="invalid_threshold")
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "threshold",
                        default=self.config_entry.options.get(
                            "threshold", DEFAULT_THRESHOLD
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                    vol.Required(
                        "lead_minutes",
                        default=self.config_entry.options.get(
                            "lead_minutes", DEFAULT_LEAD
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
                    vol.Required(
                        "max_age",
                        default=self.config_entry.options.get(
                            "max_age", DEFAULT_MAX_AGE
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=20)),
                }
            ),
        )
