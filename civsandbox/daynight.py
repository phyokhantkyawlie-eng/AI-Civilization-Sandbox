"""Calendar derived solely from fixed simulation ticks."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DayTime:
    day: int
    hour: int
    minute: int
    period: str
    darkness: int

    @property
    def daylight(self):
        return self.period in ("morning", "afternoon")


@dataclass(frozen=True)
class DayClock:
    day_ticks: int = 2400  # ten simulation minutes at 1x
    start_hour: int = 8

    def __post_init__(self):
        if type(self.day_ticks) is not int or self.day_ticks < 24:
            raise ValueError("A day must contain at least 24 ticks")
        if type(self.start_hour) is not int or not 0 <= self.start_hour < 24:
            raise ValueError("Start hour must be an integer in 0–23")

    def at(self, tick):
        minutes = self.start_hour*60 + tick*1440//self.day_ticks
        day, minute = divmod(minutes, 1440)
        hour, minute = divmod(minute, 60)
        period = "morning" if 6 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening" if 18 <= hour < 20 else "night"
        # Gradual dawn/dusk tint; cached surfaces in the renderer use this alpha.
        hour_fraction = (minutes % 1440)/60
        darkness = round(48*max(0, min(1, (6-hour_fraction)/2 if hour_fraction < 6 else (hour_fraction-18)/2)))
        return DayTime(day+1, hour, minute, period, darkness)
