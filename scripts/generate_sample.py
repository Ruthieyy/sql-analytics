#!/usr/bin/env python3
"""Write the synthetic daily weather sample checked into data/sample.

The first commit message mentions a weather dataset, but no data file was in
the repository. This script invents a small deterministic series with the
same columns as the original Athena table so the SQL can be read and run
locally. It is not an export from a weather service.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "sample"

# name, region, climate_zone, temp_base_f, humidity_base, aqi_base
CITIES = [
    ("Seattle", "West", "Marine", 44, 78, 35),
    ("Phoenix", "Southwest", "Arid", 62, 22, 55),
    ("Chicago", "Midwest", "Continental", 28, 68, 45),
    ("Miami", "Southeast", "Tropical", 70, 76, 40),
]

# Shared seasonality plus a stronger spring warm-up in Phoenix, so the
# warmest city is Miami in January and Phoenix in March.
SHARED_MONTH_BIAS_F = {1: -8, 2: 2, 3: 8}
EXTRA_MONTH_BIAS_F = {
    "Phoenix": {1: -6, 2: 0, 3: 12},
    "Miami": {1: 3, 2: 0, 3: -1},
}

START = date(2024, 1, 1)
END = date(2024, 3, 31)


def iter_days():
    day = START
    index = 0
    while day <= END:
        yield index, day
        day += timedelta(days=1)
        index += 1


def temperature(city: str, base: int, day_index: int, month: int) -> int:
    weekly = (day_index % 7) - 3  # -3..3, same calendar day for every city
    extra = EXTRA_MONTH_BIAS_F.get(city, {}).get(month, 0)
    return base + SHARED_MONTH_BIAS_F[month] + extra + weekly


def humidity(base: int, day_index: int) -> int:
    return base + (day_index % 5)


def air_quality(city: str, base: int, day_index: int) -> int:
    # A few invented spikes sit above the query threshold of 100.
    if city == "Phoenix" and day_index % 9 == 0:
        return 130
    if city == "Chicago" and day_index % 15 == 0:
        return 115
    return base


def weather_rows() -> list[dict]:
    rows = []
    for index, day in iter_days():
        for name, _region, _zone, temp_base, humidity_base, aqi_base in CITIES:
            rows.append(
                {
                    "date": day.isoformat(),
                    "city": name,
                    "temperature": temperature(name, temp_base, index, day.month),
                    "humidity": humidity(humidity_base, index),
                    "air_quality": air_quality(name, aqi_base, index),
                }
            )
    return rows


def city_rows() -> list[dict]:
    return [
        {"city": name, "region": region, "climate_zone": zone}
        for name, region, zone, *_rest in CITIES
    ]


def _month_averages(rows: list[dict]) -> dict[tuple[str, str], float]:
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in rows:
        grouped[(row["city"], row["date"][5:7])].append(row["temperature"])
    return {key: sum(values) / len(values) for key, values in grouped.items()}


def validate(rows: list[dict]) -> None:
    keys = [(row["date"], row["city"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise SystemExit("duplicate city-date rows")
    if rows[0]["date"] != START.isoformat() or rows[-1]["date"] != END.isoformat():
        raise SystemExit("unexpected date span")
    if len(rows) != 91 * len(CITIES):
        raise SystemExit(f"expected {91 * len(CITIES)} rows, found {len(rows)}")

    cities = {row["city"] for row in rows}
    if cities != {name for name, *_rest in CITIES}:
        raise SystemExit(f"unexpected cities: {cities}")

    by_city: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        by_city[row["city"]].append(row["temperature"])
        if not 0 <= row["humidity"] <= 100:
            raise SystemExit(f"humidity out of range: {row}")
        if not -20 <= row["temperature"] <= 120:
            raise SystemExit(f"temperature out of the intended demo range: {row}")

    monthly = _month_averages(rows)
    for city, temps in by_city.items():
        overall = sum(temps) / len(temps)
        for month in ("01", "02", "03"):
            gap = abs(monthly[(city, month)] - overall)
            if gap < 0.5:
                raise SystemExit(
                    f"{city} month {month} average is only {gap:.3f} from the city average"
                )

    for month in ("01", "02", "03"):
        averages = sorted(monthly[(city, month)] for city in cities)
        closest = min(b - a for a, b in zip(averages, averages[1:]))
        if closest < 0.5:
            raise SystemExit(f"month {month} city averages are too close: {averages}")

    def warmest(month: str) -> str:
        return max(cities, key=lambda city: monthly[(city, month)])

    if warmest("01") != "Miami" or warmest("03") != "Phoenix":
        raise SystemExit(
            f"expected Miami warmest in January and Phoenix in March, "
            f"found {warmest('01')} and {warmest('03')}"
        )

    poor = [row for row in rows if row["air_quality"] > 100]
    poor_cities = {row["city"] for row in poor}
    if poor_cities != {"Phoenix", "Chicago"}:
        raise SystemExit(f"unexpected poor-air cities: {poor_cities}")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_sample(directory: Path = SAMPLE_DIR) -> None:
    rows = weather_rows()
    validate(rows)
    write_csv(
        directory / "weather.csv",
        ["date", "city", "temperature", "humidity", "air_quality"],
        rows,
    )
    write_csv(
        directory / "cities.csv",
        ["city", "region", "climate_zone"],
        city_rows(),
    )


if __name__ == "__main__":
    write_sample()
    rows = weather_rows()
    poor = sum(row["air_quality"] > 100 for row in rows)
    print(f"wrote {SAMPLE_DIR / 'weather.csv'} ({len(rows)} rows) and cities.csv")
    print(f"poor air_quality days: {poor}")
