-- 7-day rolling average temperature by city, with a partial window on the earliest days.
SELECT
  city,
  observation_date,
  temperature,
  ROUND(AVG(temperature) OVER (
    PARTITION BY city
    ORDER BY observation_date
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
  ), 1) AS rolling_7d_avg
FROM data_lake.weather_parquet
ORDER BY city, observation_date;
