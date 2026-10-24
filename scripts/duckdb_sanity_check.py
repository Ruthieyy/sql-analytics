#!/usr/bin/env python3
"""Run the query files locally with DuckDB against the sample CSVs.

Athena DDL (the external tables and the CTAS storage clause) is not executed
here. The script loads the sample, applies the SELECT from the Parquet CTAS,
and runs each file in sql/queries. No AWS calls.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "sample"
QUERY_DIR = ROOT / "sql" / "queries"
CTAS_PATH = ROOT / "sql" / "ddl" / "03_weather_parquet_ctas.sql"

WEATHER_COLUMNS = """{
  'date': 'VARCHAR',
  'city': 'VARCHAR',
  'temperature': 'INTEGER',
  'humidity': 'INTEGER',
  'air_quality': 'INTEGER'
}"""

CITY_COLUMNS = """{
  'city': 'VARCHAR',
  'region': 'VARCHAR',
  'climate_zone': 'VARCHAR'
}"""


def ctas_select_sql() -> str:
    """Return the SELECT body of the Athena CTAS so DuckDB runs that projection."""
    text = CTAS_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"\)\s+AS\s+(SELECT\b.*)\s*;\s*\Z",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise RuntimeError(f"{CTAS_PATH} has no AS SELECT body")
    return match.group(1).strip()


def query_files() -> list[Path]:
    return sorted(QUERY_DIR.glob("*.sql"))


def purpose(sql: str) -> str:
    line = sql.lstrip().splitlines()[0]
    if not line.startswith("-- "):
        raise ValueError("query is missing a one-line purpose comment")
    return line[3:].strip()


def _load_csv(con: duckdb.DuckDBPyConnection, table: str, path: Path, columns_sql: str) -> None:
    escaped = path.as_posix().replace("'", "''")
    con.execute(
        f"""
        CREATE TABLE data_lake.{table} AS
        SELECT * FROM read_csv(
          '{escaped}',
          header = true,
          columns = {columns_sql}
        )
        """
    )


def load_sample(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS data_lake")
    _load_csv(con, "weather", SAMPLE_DIR / "weather.csv", WEATHER_COLUMNS)
    _load_csv(con, "cities", SAMPLE_DIR / "cities.csv", CITY_COLUMNS)
    con.execute("CREATE TABLE data_lake.weather_parquet AS " + ctas_select_sql())


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    load_sample(con)
    return con


def run_queries(con: duckdb.DuckDBPyConnection) -> list[tuple[Path, str, list[tuple]]]:
    results = []
    for path in query_files():
        sql = path.read_text(encoding="utf-8")
        comment = purpose(sql)
        rows = con.execute(sql).fetchall()
        if not rows:
            raise RuntimeError(f"{path.name} returned no rows")
        results.append((path, comment, rows))
    return results


def format_value(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def main() -> int:
    if len(query_files()) != 7:
        print(f"expected 7 query files, found {len(query_files())}", file=sys.stderr)
        return 1
    con = connect()
    try:
        results = run_queries(con)
    except Exception as exc:  # noqa: BLE001 — CLI should report the failing statement
        print(f"sanity check failed: {exc}", file=sys.stderr)
        return 1
    weather_rows = con.execute("SELECT count(*) FROM data_lake.weather_parquet").fetchone()[0]
    print(f"weather_parquet rows: {weather_rows}")
    for path, comment, rows in results:
        print(f"{path.name}: {comment} ({len(rows)} rows)")
        if len(rows) <= 40:
            for row in rows:
                rendered = ", ".join(format_value(value) for value in row)
                print(f"  {rendered}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
