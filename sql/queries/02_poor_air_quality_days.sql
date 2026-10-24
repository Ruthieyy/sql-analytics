-- Days with air_quality above 100, worst first.
SELECT
  observation_date,
  city,
  air_quality
FROM data_lake.weather_parquet
WHERE air_quality > 100
ORDER BY air_quality DESC, observation_date, city;
