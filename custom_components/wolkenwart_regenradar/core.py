"""Time and forecast model independent of Home Assistant."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

STEP = 300
PUBLICATION_DELAY = 250


def target_release(now: datetime, offset: int = 0) -> datetime:
    value = math.floor((now.timestamp() - PUBLICATION_DELAY - offset) / STEP) * STEP
    return datetime.fromtimestamp(value, UTC)


@dataclass(frozen=True, slots=True)
class Forecast:
    release: datetime
    amounts: tuple[float, ...]

    def __post_init__(self):
        if self.release.tzinfo is None or len(self.amounts) != 25:
            raise ValueError("Invalid forecast structure")
        if any(not math.isfinite(x) or x < 0 for x in self.amounts):
            raise ValueError("Invalid precipitation amount")

    @property
    def start(self):
        return self.release - timedelta(seconds=STEP)

    @property
    def end(self):
        return self.release + timedelta(hours=2)

    def deadline(self, max_age_minutes: int):
        return self.start + timedelta(minutes=max_age_minutes)

    def valid(self, now: datetime, max_age_minutes: int):
        return self.release <= now < self.deadline(max_age_minutes)

    def windows(self):
        for index, amount in enumerate(self.amounts):
            start = self.start + timedelta(seconds=index * STEP)
            yield start, start + timedelta(seconds=STEP), amount

    def rain_start(self, now: datetime, threshold: float):
        return next(
            (
                start
                for start, end, amount in self.windows()
                if end > now and amount * 12 > threshold
            ),
            None,
        )

    def next_hour(self, now: datetime):
        end_at = now + timedelta(hours=1)
        overlapping = [
            (max(0, (min(end, end_at) - max(start, now)).total_seconds()), amount)
            for start, end, amount in self.windows()
            if start < end_at and end > now
        ]
        amount = sum(seconds / STEP * value for seconds, value in overlapping)
        peak = max((value * 12 for _, value in overlapping), default=0)
        return round(amount, 4), round(peak, 4)

    def series(self):
        return [
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "amount_mm": amount,
                "intensity_mmh": round(amount * 12, 4),
            }
            for start, end, amount in self.windows()
        ]


def data_status(
    forecast: Forecast | None, now: datetime, max_age: int, offset: int = 0
):
    if forecast is None:
        return "no_data"
    if not forecast.valid(now, max_age):
        return "expired"
    return "current" if forecast.release >= target_release(now, offset) else "cached"
