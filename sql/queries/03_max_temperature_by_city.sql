-- Highest temperature recorded for each city.
SELECT
  city,
  MAX(temperature) AS max_temp
FROM data_lake.weather_parquet
GROUP BY city
ORDER BY max_temp DESC, city;
