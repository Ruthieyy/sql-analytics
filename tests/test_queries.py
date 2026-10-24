"""Check the sample, the CTAS projection, and each query file with DuckDB."""

from __future__ import annotations

import csv
import importlib.util
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "sample"

EXPECTED_QUERIES = [
    "01_avg_temperature_by_city.sql",
    "02_poor_air_quality_days.sql",
    "03_max_temperature_by_city.sql",
    "04_rank_cities_by_month.sql",
    "05_rolling_7day_avg_temperature.sql",
    "06_observations_with_climate_zone.sql",
    "07_months_above_city_average.sql",
]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sanity = _load("duckdb_sanity_check", ROOT / "scripts" / "duckdb_sanity_check.py")
sample = _load("generate_sample", ROOT / "scripts" / "generate_sample.py")


def _read_weather() -> list[dict]:
    rows = []
    with (SAMPLE_DIR / "weather.csv").open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            rows.append(
                {
                    "date": record["date"],
                    "observation_date": date.fromisoformat(record["date"]),
                    "city": record["city"],
                    "temperature": int(record["temperature"]),
                    "humidity": int(record["humidity"]),
                    "air_quality": int(record["air_quality"]),
                    "year": record["date"][0:4],
                    "month": record["date"][5:7],
                }
            )
    return rows


def _read_cities() -> dict[str, dict]:
    with (SAMPLE_DIR / "cities.csv").open(newline="", encoding="utf-8") as handle:
        return {record["city"]: record for record in csv.DictReader(handle)}


def _rounded(con, value: float):
    return con.execute("SELECT ROUND(?, 1)", [value]).fetchone()[0]


@pytest.fixture(scope="module")
def con():
    return sanity.connect()


@pytest.fixture(scope="module")
def weather_rows():
    return _read_weather()


def test_committed_sample_matches_generator(tmp_path):
    sample.write_sample(tmp_path)
    for name in ("weather.csv", "cities.csv"):
        assert (tmp_path / name).read_bytes() == (SAMPLE_DIR / name).read_bytes()


def test_query_files_have_one_purpose_comment():
    found = [path.name for path in sanity.query_files()]
    assert found == EXPECTED_QUERIES
    blob = []
    for path in sanity.query_files():
        text = path.read_text(encoding="utf-8")
        lines = text.strip().splitlines()
        assert lines[0].startswith("-- ")
        assert len(lines[0]) > 12
        comments = [line for line in lines if line.strip().startswith("--")]
        assert comments == [lines[0]]
        blob.append(text.lower())
    combined = "\n".join(blob)
    assert re.search(r"\bjoin\b", combined)
    assert re.search(r"\bwith\b", combined)
    assert " over (" in combined
    assert "rank()" in combined
    assert "rows between 6 preceding and current row" in combined


def test_ddl_keeps_csv_and_adds_partitioned_parquet():
    database = (ROOT / "sql/ddl/00_create_database.sql").read_text(encoding="utf-8")
    weather = (ROOT / "sql/ddl/01_weather_csv_external_table.sql").read_text(encoding="utf-8")
    cities = (ROOT / "sql/ddl/02_cities_csv_external_table.sql").read_text(encoding="utf-8")
    ctas = (ROOT / "sql/ddl/03_weather_parquet_ctas.sql").read_text(encoding="utf-8")
    assert "CREATE DATABASE IF NOT EXISTS data_lake" in database
    assert "CREATE EXTERNAL TABLE IF NOT EXISTS data_lake.weather" in weather
    assert "FIELDS TERMINATED BY ','" in weather
    assert "skip.header.line.count" in weather
    assert "s3://your-bucket/weather/raw/" in weather
    assert "CREATE EXTERNAL TABLE IF NOT EXISTS data_lake.cities" in cities
    assert "format = 'PARQUET'" in ctas
    assert "parquet_compression = 'SNAPPY'" in ctas
    assert "partitioned_by = ARRAY['year', 'month']" in ctas
    select_sql = sanity.ctas_select_sql()
    projection, _from, source = select_sql.partition("FROM")
    assert projection.rstrip().endswith("substr(date, 6, 2) AS month")
    assert "substr(date, 1, 4) AS year" in projection
    assert source.strip() == "data_lake.weather"


def test_parquet_projection_and_hive_folders(con, tmp_path, weather_rows):
    count, cities = con.execute(
        """
        SELECT count(*), count(DISTINCT city)
        FROM data_lake.weather_parquet
        """
    ).fetchone()
    assert count == len(weather_rows) == 364
    assert cities == 4
    mismatch = con.execute(
        """
        SELECT count(*)
        FROM data_lake.weather_parquet
        WHERE year <> substr(CAST(observation_date AS VARCHAR), 1, 4)
           OR month <> substr(CAST(observation_date AS VARCHAR), 6, 2)
        """
    ).fetchone()[0]
    assert mismatch == 0

    output = tmp_path / "parquet"
    con.execute(
        f"""
        COPY ({sanity.ctas_select_sql()}) TO '{output.as_posix()}'
        (FORMAT PARQUET, PARTITION_BY (year, month), COMPRESSION SNAPPY)
        """
    )
    folders = sorted(
        {path.relative_to(output).parent.as_posix() for path in output.rglob("*.parquet")}
    )
    assert folders == [
        "year=2024/month=01",
        "year=2024/month=02",
        "year=2024/month=03",
    ]
    counted = con.execute(
        f"""
        SELECT month, count(*)
        FROM read_parquet('{output.as_posix()}/**/*.parquet', hive_partitioning = true)
        GROUP BY month
        ORDER BY month
        """
    ).fetchall()
    assert [(str(month).zfill(2), n) for month, n in counted] == [
        ("01", 124),
        ("02", 116),
        ("03", 124),
    ]


def test_avg_and_max_match_sample(con, weather_rows):
    by_city = defaultdict(list)
    for row in weather_rows:
        by_city[row["city"]].append(row["temperature"])
    expected_avg = sorted(
        ((city, sum(temps) / len(temps)) for city, temps in by_city.items()),
        key=lambda item: (-item[1], item[0]),
    )
    actual_avg = con.execute(
        (ROOT / "sql/queries/01_avg_temperature_by_city.sql").read_text(encoding="utf-8")
    ).fetchall()
    assert [row[0] for row in actual_avg] == [city for city, _avg in expected_avg]
    for (_city, actual), (_name, mean) in zip(actual_avg, expected_avg):
        assert abs(float(actual) - float(_rounded(con, mean))) < 1e-9

    expected_max = sorted(
        ((city, max(temps)) for city, temps in by_city.items()),
        key=lambda item: (-item[1], item[0]),
    )
    actual_max = con.execute(
        (ROOT / "sql/queries/03_max_temperature_by_city.sql").read_text(encoding="utf-8")
    ).fetchall()
    assert actual_max == expected_max


def test_poor_air_quality_filter(con, weather_rows):
    expected = sorted(
        (
            (row["observation_date"], row["city"], row["air_quality"])
            for row in weather_rows
            if row["air_quality"] > 100
        ),
        key=lambda item: (-item[2], item[0], item[1]),
    )
    actual = con.execute(
        (ROOT / "sql/queries/02_poor_air_quality_days.sql").read_text(encoding="utf-8")
    ).fetchall()
    assert actual == expected
    assert actual
    assert {row[1] for row in actual} == {"Phoenix", "Chicago"}
    assert all(air_quality > 100 for _day, _city, air_quality in actual)


def test_monthly_rank(con, weather_rows):
    grouped = defaultdict(list)
    for row in weather_rows:
        grouped[(row["year"], row["month"], row["city"])].append(row["temperature"])
    by_month = defaultdict(list)
    for (year, month, city), temps in grouped.items():
        by_month[(year, month)].append((city, sum(temps) / len(temps)))

    expected = []
    for (year, month), items in sorted(by_month.items()):
        ordered = sorted(items, key=lambda item: (-item[1], item[0]))
        for rank, (city, mean) in enumerate(ordered, start=1):
            expected.append((year, month, city, mean, rank))

    actual = con.execute(
        (ROOT / "sql/queries/04_rank_cities_by_month.sql").read_text(encoding="utf-8")
    ).fetchall()
    assert len(actual) == 12
    for got, (year, month, city, mean, rank) in zip(actual, expected):
        assert got[0] == year
        assert got[1] == month
        assert got[2] == city
        assert abs(float(got[3]) - float(_rounded(con, mean))) < 1e-9
        assert got[4] == rank
    january = [row[2] for row in actual if row[1] == "01"]
    march = [row[2] for row in actual if row[1] == "03"]
    assert january[0] == "Miami"
    assert march[0] == "Phoenix"


def test_rolling_average(con, weather_rows):
    by_city = defaultdict(list)
    for row in weather_rows:
        by_city[row["city"]].append(row)
    expected = []
    for city, items in sorted(by_city.items()):
        items = sorted(items, key=lambda row: row["observation_date"])
        temps = [row["temperature"] for row in items]
        for index, row in enumerate(items):
            window = temps[max(0, index - 6) : index + 1]
            expected.append(
                (city, row["observation_date"], row["temperature"], sum(window) / len(window), len(window))
            )

    actual = con.execute(
        (ROOT / "sql/queries/05_rolling_7day_avg_temperature.sql").read_text(encoding="utf-8")
    ).fetchall()
    assert len(actual) == len(expected) == 364
    for got, (city, day, temperature, mean, window_len) in zip(actual, expected):
        assert got[0] == city
        assert got[1] == day
        assert got[2] == temperature
        assert abs(float(got[3]) - float(_rounded(con, mean))) < 1e-9
        if window_len == 1:
            assert got[3] == temperature


def test_city_join(con, weather_rows):
    cities = _read_cities()
    expected = [
        (
            row["observation_date"],
            row["city"],
            cities[row["city"]]["region"],
            cities[row["city"]]["climate_zone"],
            row["temperature"],
            row["humidity"],
            row["air_quality"],
        )
        for row in sorted(weather_rows, key=lambda row: (row["observation_date"], row["city"]))
    ]
    actual = con.execute(
        (ROOT / "sql/queries/06_observations_with_climate_zone.sql").read_text(encoding="utf-8")
    ).fetchall()
    assert actual == expected
    assert len({row[3] for row in actual}) == 4


def test_months_above_city_average(con, weather_rows):
    by_city = defaultdict(list)
    by_month = defaultdict(list)
    for row in weather_rows:
        by_city[row["city"]].append(row["temperature"])
        by_month[(row["city"], row["year"], row["month"])].append(row["temperature"])
    overall = {city: sum(temps) / len(temps) for city, temps in by_city.items()}
    expected = []
    for (city, year, month), temps in by_month.items():
        month_avg = sum(temps) / len(temps)
        if month_avg > overall[city]:
            expected.append((city, year, month, month_avg, overall[city]))
    expected.sort()

    actual = con.execute(
        (ROOT / "sql/queries/07_months_above_city_average.sql").read_text(encoding="utf-8")
    ).fetchall()
    assert len(actual) == len(expected)
    for got, (city, year, month, month_avg, overall_avg) in zip(actual, expected):
        assert (got[0], got[1], got[2]) == (city, year, month)
        assert abs(float(got[3]) - float(_rounded(con, month_avg))) < 1e-9
        assert abs(float(got[4]) - float(_rounded(con, overall_avg))) < 1e-9
        assert float(got[3]) > float(got[4])
    assert all(row[2] != "01" for row in actual)


def test_sanity_script_exits_zero():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "duckdb_sanity_check.py")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    for name in EXPECTED_QUERIES:
        assert name in result.stdout
