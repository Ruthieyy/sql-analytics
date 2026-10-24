-- Average temperature by city, warmest first.
SELECT
  city,
  ROUND(AVG(temperature), 1) AS avg_temp
FROM data_lake.weather_parquet
GROUP BY city
ORDER BY avg_temp DESC, city;
