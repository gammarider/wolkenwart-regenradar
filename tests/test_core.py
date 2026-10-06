from datetime import UTC, datetime, timedelta

import pytest

from custom_components.wolkenwart_regenradar.core import (
    Forecast,
    data_status,
    target_release,
)

T = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("offset", [0, 15, 30])
def test_publication_boundary(offset):
    at = T + timedelta(seconds=250 + offset)
    assert target_release(at - timedelta(microseconds=1), offset) == T - timedelta(
        minutes=5
    )
    assert target_release(at, offset) == T


@pytest.mark.parametrize(
    "age,status",
    [
        (0, "expired"),
        (300, "current"),
        (600, "current"),
        (900, "cached"),
        (1199, "cached"),
        (1200, "expired"),
        (3600, "expired"),
    ],
)
def test_fixed_expiry(age, status):
    f = Forecast(T, (0.0,) * 25)
    now = f.start + timedelta(seconds=age)
    assert data_status(f, now, 20) == status
    assert data_status(None, now, 20) == "no_data"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1])
def test_invalid_values_rejected(bad):
    with pytest.raises(ValueError):
        Forecast(T, (bad,) * 25)


def test_future_time_and_incomplete_horizon_rejected():
    with pytest.raises(ValueError):
        Forecast(T, (0.0,) * 24)
    with pytest.raises(ValueError):
        Forecast(T.replace(tzinfo=None), (0.0,) * 25)
    assert not Forecast(T, (0.0,) * 25).valid(T - timedelta(seconds=1), 20)


def test_old_wet_windows_do_not_keep_rain_on():
    f = Forecast(T, (1.0,) + (0.0,) * 24)
    assert f.rain_start(T, 0.1) is None
    assert f.next_hour(T) == (0.0, 0.0)


def test_future_front_and_rain_threshold():
    f = Forecast(T, (0.0,) * 5 + (0.1,) * 3 + (0.0,) * 17)
    assert f.rain_start(T, 1.19) == T + timedelta(minutes=20)
    assert f.rain_start(T, 1.21) is None
    assert f.next_hour(T) == (0.3, 1.2)


def test_partial_first_window_and_horizon_are_time_based():
    f = Forecast(T, (1.0,) * 25)
    assert f.next_hour(T + timedelta(seconds=150)) == (12.0, 12.0)
    assert f.rain_start(T + timedelta(minutes=120), 0) is None
    assert f.series()[0]["start"] == (T - timedelta(minutes=5)).isoformat()
