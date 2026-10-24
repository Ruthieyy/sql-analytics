# Weather queries for Athena

Daily weather rows land in S3 as CSV. Athena reads that file through an external table, a CTAS writes a Snappy Parquet table partitioned by year and month, and the queries in `sql/queries` run against the Parquet table. A DuckDB script runs those same query files on the sample in this repo.

## Dataset

The repository did not contain the weather file named in the first commit. The CSVs here are a synthetic sample written by `scripts/generate_sample.py` (4 cities, 1 January 2024 through 31 March 2024, including 29 February). `data/sample/weather.csv` has 364 data rows. `data/sample/cities.csv` is the whole city lookup.

Regenerate both files with:

```bash
python scripts/generate_sample.py
```

`weather.csv` columns:

| Column | CSV table type | Meaning |
| --- | --- | --- |
| `date` | STRING `YYYY-MM-DD` | Observation day |
| `city` | STRING | Seattle, Phoenix, Chicago, or Miami |
| `temperature` | INT | Daily temperature in degrees Fahrenheit |
| `humidity` | INT | Relative humidity percent |
| `air_quality` | INT | Integer index used by the filter `air_quality > 100` |

First day of `data/sample/weather.csv`:

```text
date,city,temperature,humidity,air_quality
2024-01-01,Seattle,33,78,35
2024-01-01,Phoenix,45,22,130
2024-01-01,Chicago,17,68,115
2024-01-01,Miami,62,76,40
```

`cities.csv`:

```text
city,region,climate_zone
Seattle,West,Marine
Phoenix,Southwest,Arid
Chicago,Midwest,Continental
Miami,Southeast,Tropical
```

Eighteen rows have `air_quality` above 100: Phoenix on 130 and Chicago on 115. Seattle stays at 35 and Miami stays at 40. The placement of those days is in `scripts/generate_sample.py`. On this sample, Miami has the highest monthly average temperature in January and February, and Phoenix has the highest in March.

## Load the sample to S3

Replace `your-bucket` here and in `sql/ddl/01_weather_csv_external_table.sql`, `sql/ddl/02_cities_csv_external_table.sql`, and `sql/ddl/03_weather_parquet_ctas.sql`. The earlier SQL referenced `s3://yu-data-lake-test/weather/`, which is not part of this repo.

```bash
aws s3 cp data/sample/weather.csv s3://your-bucket/weather/raw/weather.csv
aws s3 cp data/sample/cities.csv s3://your-bucket/weather/cities/cities.csv
```

Leave those prefixes otherwise empty. Each external table reads its whole prefix. The Athena workgroup needs to read both prefixes, write `s3://your-bucket/weather/parquet/`, and write its query results.

Run these files one at a time, in order. Each file is a single statement:

1. `sql/ddl/00_create_database.sql` creates `data_lake`.
2. `sql/ddl/01_weather_csv_external_table.sql` creates `data_lake.weather` over the raw CSV. The header is skipped with `skip.header.line.count`.
3. `sql/ddl/02_cities_csv_external_table.sql` creates `data_lake.cities`.
4. `sql/ddl/03_weather_parquet_ctas.sql` creates `data_lake.weather_parquet`.

The CTAS casts `date` to `observation_date` (DATE) and adds `year` and `month` as the last two columns. Those two columns are the partitions. Athena writes them as Hive-style prefixes such as `year=2024/month=01/`. The destination prefix must be empty. To run the CTAS again, drop `data_lake.weather_parquet` and delete `s3://your-bucket/weather/parquet/` first. Dropping the table leaves the objects in that prefix.

## Queries

Run these after the CTAS. Every file reads `data_lake.weather_parquet`. The join also reads `data_lake.cities`. The first line of each file is the purpose comment.

| File | Purpose |
| --- | --- |
| `sql/queries/01_avg_temperature_by_city.sql` | Average temperature by city, warmest first. |
| `sql/queries/02_poor_air_quality_days.sql` | Days with air_quality above 100, worst first. |
| `sql/queries/03_max_temperature_by_city.sql` | Highest temperature recorded for each city. |
| `sql/queries/04_rank_cities_by_month.sql` | Rank cities within each month by average temperature (1 is warmest). |
| `sql/queries/05_rolling_7day_avg_temperature.sql` | 7-day rolling average temperature by city, with a partial window on the earliest days. |
| `sql/queries/06_observations_with_climate_zone.sql` | Daily observations joined to each city's region and climate zone. |
| `sql/queries/07_months_above_city_average.sql` | Months when a city's average temperature was above its own all-period average. |

Files 01–03 are the original city average, poor-air filter, and city maximum, pointed at `weather_parquet`. File 04 aggregates in a CTE and ranks with `RANK`. File 05 uses a 7-row window frame. File 06 joins the city lookup. File 07 compares two CTE aggregates.

## Check the SQL locally

From the repo root, with the versions pinned in `requirements.txt`:

```bash
python -m pip install -r requirements.txt
python scripts/duckdb_sanity_check.py
python -m pytest -q
```

`scripts/duckdb_sanity_check.py` loads the sample CSVs, builds `data_lake.weather_parquet` with the SELECT from the CTAS file, and runs every file in `sql/queries`. It prints each purpose line and, for results of 40 rows or fewer, the rows. It does not call AWS.

`tests/test_queries.py` checks the committed CSVs against the generator, checks that each query file has one purpose comment, and compares each query to a separate aggregation of the CSV. It also writes the CTAS SELECT to partitioned Parquet in a temporary directory and expects `year=2024/month=01`, `month=02`, and `month=03`.

## Limitations / Next steps

- The sample is synthetic: four cities and three months, with invented temperature, humidity, and air-quality values. It is not a station feed, a climate normal, or a regulatory air-quality product.
- The DDL is written for Athena engine version 3. Nothing in this repo connects to AWS, so a live workgroup is still the check for the CSV SerDe, catalog registration, and the CTAS storage clause. The local check covers the CTAS SELECT and the query files.
- The CSV tables are not partitioned. Partitioning is the Parquet CTAS, which rewrites the full sample in one statement. There is no incremental insert, compaction, or partition projection.
- The landing format is unquoted comma-separated text with a header row. That matches this sample, which has no commas inside fields.
- `air_quality > 100` is the cutoff in `sql/queries/02_poor_air_quality_days.sql`. It is not tied to a published index definition.
- Humidity is stored on the Parquet table and returned by the join. No query aggregates it.
- Next: replace the synthetic CSVs with a real observation feed, add partition projection on `year` and `month`, and load new days with `INSERT INTO data_lake.weather_parquet` instead of rewriting the prefix. Reject duplicate city-date keys, and reject air-quality values outside a range you choose, before that load.
