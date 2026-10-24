-- Daily observations joined to each city's region and climate zone.
SELECT
  weather.observation_date,
  weather.city,
  cities.region,
  cities.climate_zone,
  weather.temperature,
  weather.humidity,
  weather.air_quality
FROM data_lake.weather_parquet AS weather
JOIN data_lake.cities AS cities
  ON weather.city = cities.city
ORDER BY weather.observation_date, weather.city;
