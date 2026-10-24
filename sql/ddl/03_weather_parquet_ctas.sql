-- Convert the CSV landing table to Snappy Parquet partitioned by year and month.
-- Partition columns are last, which this CTAS form requires. Drop data_lake.weather_parquet and delete the external_location prefix before re-running.
CREATE TABLE data_lake.weather_parquet
WITH (
  format = 'PARQUET',
  parquet_compression = 'SNAPPY',
  external_location = 's3://your-bucket/weather/parquet/',
  partitioned_by = ARRAY['year', 'month']
) AS
SELECT
  CAST(date AS DATE) AS observation_date,
  city,
  temperature,
  humidity,
  air_quality,
  substr(date, 1, 4) AS year,
  substr(date, 6, 2) AS month
FROM data_lake.weather;
