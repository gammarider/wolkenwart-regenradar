import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.wolkenwart_regenradar.const import DOMAIN
from custom_components.wolkenwart_regenradar.core import Forecast
from custom_components.wolkenwart_regenradar.radar import RadarError

T = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


async def setup(hass, freezer, error=False):
    freezer.move_to(T + timedelta(seconds=280))
    e = MockConfigEntry(
        domain=DOMAIN,
        title="Test radar",
        data={"name": "Test radar", "latitude": 48.8, "longitude": 9.2},
    )
    e.add_to_hass(hass)
    f = Forecast(T, (0.0,) * 5 + (0.2,) * 3 + (0.0,) * 17)
    with patch(
        "custom_components.wolkenwart_regenradar.coordinator.download",
        new=AsyncMock(side_effect=RadarError("DWD HTTP 404"))
        if error
        else AsyncMock(return_value=b"data"),
    ):
        with patch(
            "custom_components.wolkenwart_regenradar.coordinator.decode_archive",
            return_value=f,
        ):
            assert await hass.config_entries.async_setup(e.entry_id)
            await hass.async_block_till_done()
    return e


def states(hass):
    return {
        s.entity_id: s
        for s in hass.states.async_all()
        if s.entity_id.startswith(("sensor.test_radar", "binary_sensor.test_radar"))
    }


async def test_real_setup_nine_entities_and_unload(hass, freezer):
    e = await setup(hass, freezer)
    assert e.state == ConfigEntryState.LOADED
    s = states(hass)
    assert len(s) == 9
    assert s["binary_sensor.test_radar_precipitation_expected"].state == "on"
    assert s["binary_sensor.test_radar_rain_protection_due"].state == "off"
    assert s["sensor.test_radar_data_status"].state == "current"
    assert (
        s["sensor.test_radar_planned_protection_time"].state
        == "2026-10-06T12:05:00+00:00"
    )
    c = e.runtime_data
    assert await hass.config_entries.async_unload(e.entry_id)
    assert c._stopped and not c._timers


async def test_start_without_data_diagnostics_loaded(hass, freezer):
    e = await setup(hass, freezer, error=True)
    s = states(hass)
    assert e.state == ConfigEntryState.LOADED
    assert s["sensor.test_radar_data_status"].state == "no_data"
    assert s["binary_sensor.test_radar_precipitation_expected"].state == "unavailable"
    assert s["sensor.test_radar_data_status"].attributes["last_error"] == "DWD HTTP 404"


async def test_short_outage_keeps_plan_then_exact_expiry(hass, freezer):
    e = await setup(hass, freezer)
    c = e.runtime_data
    c._unsub_refresh()
    freezer.move_to(T + timedelta(minutes=10))
    with patch(
        "custom_components.wolkenwart_regenradar.coordinator.download",
        new=AsyncMock(side_effect=RadarError("DWD HTTP 503")),
    ) as fetch:
        await c.async_refresh()
        c._unsub_refresh()
        assert fetch.await_count == 1 and c.usable
        assert c.next_attempt == T + timedelta(minutes=11)
        await c.async_refresh()
        c._unsub_refresh()
        assert fetch.await_count == 1
    assert states(hass)["sensor.test_radar_data_status"].state == "cached"
    assert states(hass)["binary_sensor.test_radar_rain_protection_due"].state == "on"
    freezer.move_to(T + timedelta(minutes=15))
    async_fire_time_changed(hass, T + timedelta(minutes=15))
    await hass.async_block_till_done()
    assert states(hass)["sensor.test_radar_data_status"].state == "expired"
    assert (
        states(hass)["binary_sensor.test_radar_precipitation_expected"].state
        == "unavailable"
    )
    assert (
        states(hass)["sensor.test_radar_planned_protection_time"].state == "unavailable"
    )


async def test_hung_request_cannot_block_expiry(hass, freezer):
    e = await setup(hass, freezer)
    c = e.runtime_data
    c._unsub_refresh()
    freezer.move_to(T + timedelta(minutes=14, seconds=59))
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hang(*args):
        entered.set()
        await release.wait()
        raise RadarError("network unavailable")

    with patch(
        "custom_components.wolkenwart_regenradar.coordinator.download", new=hang
    ):
        task = asyncio.create_task(c.async_refresh())
        await entered.wait()
        freezer.move_to(T + timedelta(minutes=15))
        async_fire_time_changed(hass, T + timedelta(minutes=15))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert (
            states(hass)["binary_sensor.test_radar_precipitation_expected"].state
            == "unavailable"
        )
        release.set()
        await task
        c._unsub_refresh()
    assert not c.usable


async def test_recovery_replaces_old_plan_with_fresh_dry_forecast(hass, freezer):
    e = await setup(hass, freezer)
    c = e.runtime_data
    c._unsub_refresh()
    freezer.move_to(T + timedelta(minutes=10))
    dry = Forecast(T + timedelta(minutes=5), (0.0,) * 25)
    with patch(
        "custom_components.wolkenwart_regenradar.coordinator.download",
        new=AsyncMock(return_value=b"new"),
    ):
        with patch(
            "custom_components.wolkenwart_regenradar.coordinator.decode_archive",
            return_value=dry,
        ):
            await c.async_refresh()
            c._unsub_refresh()
    assert (
        states(hass)["binary_sensor.test_radar_precipitation_expected"].state == "off"
    )
    assert states(hass)["sensor.test_radar_planned_protection_time"].state == "unknown"


async def test_late_response_does_not_extend_validity(hass, freezer):
    e = await setup(hass, freezer)
    c = e.runtime_data
    c._unsub_refresh()
    freezer.move_to(T + timedelta(minutes=10))

    async def slow(*args):
        freezer.move_to(T + timedelta(minutes=21))
        return b"late"

    with patch(
        "custom_components.wolkenwart_regenradar.coordinator.download", new=slow
    ):
        with patch(
            "custom_components.wolkenwart_regenradar.coordinator.decode_archive",
            return_value=Forecast(T + timedelta(minutes=5), (0.0,) * 25),
        ):
            await c.async_refresh()
            c._unsub_refresh()
    assert not c.usable and c.last_error == "Forecast expired during request"
    assert c.forecast.release == T


async def test_config_flow_and_duplicate(hass):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert r["type"] == FlowResultType.FORM
    with patch(
        "custom_components.wolkenwart_regenradar.async_setup_entry", return_value=True
    ):
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"],
            user_input={"name": "Garden", "latitude": 48.8, "longitude": 9.2},
        )
        assert r["type"] == FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        user_input={"name": "Duplicate", "latitude": 48.8, "longitude": 9.2},
    )
    assert r["type"] == FlowResultType.ABORT and r["reason"] == "already_configured"


async def test_outside_coverage_flow(hass):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        user_input={"name": "Elsewhere", "latitude": 0.0, "longitude": 0.0},
    )
    assert r["errors"] == {"base": "outside_coverage"}


async def test_protection_timer_exact_boundary(hass, freezer):
    e = await setup(hass, freezer)
    c = e.runtime_data
    c._unsub_refresh()
    freezer.move_to(T + timedelta(minutes=5))
    async_fire_time_changed(hass, T + timedelta(minutes=5))
    await hass.async_block_till_done()
    assert states(hass)["binary_sensor.test_radar_rain_protection_due"].state == "on"
    assert states(hass)["sensor.test_radar_data_status"].state == "current"


async def test_repeated_failures_keep_retrying_after_expiry(hass, freezer):
    e = await setup(hass, freezer)
    c = e.runtime_data
    c._unsub_refresh()
    with patch(
        "custom_components.wolkenwart_regenradar.coordinator.download",
        new=AsyncMock(side_effect=RadarError("DWD HTTP 404")),
    ) as fetch:
        for minute in range(10, 71):
            freezer.move_to(T + timedelta(minutes=minute))
            await c.async_refresh()
            c._unsub_refresh()
            assert c.next_attempt == T + timedelta(minutes=minute + 1)
        assert fetch.await_count == 61
    assert states(hass)["sensor.test_radar_data_status"].state == "expired"
    assert (
        states(hass)["binary_sensor.test_radar_precipitation_expected"].state
        == "unavailable"
    )


async def test_options_flow_keeps_location_and_changes_settings(hass, freezer):
    e = await setup(hass, freezer)
    original = dict(e.data)
    r = await hass.config_entries.options.async_init(e.entry_id)
    assert r["type"] == FlowResultType.FORM
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        new=AsyncMock(return_value=True),
    ):
        r = await hass.config_entries.options.async_configure(
            r["flow_id"],
            user_input={"threshold": 0.3, "lead_minutes": 10, "max_age": 15},
        )
        await hass.async_block_till_done()
    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert e.options == {"threshold": 0.3, "lead_minutes": 10, "max_age": 15}
    assert e.data == original
