-- Months when a city's average temperature was above its own all-period average.
WITH city_overall AS (
  SELECT
    city,
    AVG(temperature) AS overall_avg
  FROM data_lake.weather_parquet
  GROUP BY city
),
city_month AS (
  SELECT
    city,
    year,
    month,
    AVG(temperature) AS month_avg
  FROM data_lake.weather_parquet
  GROUP BY city, year, month
)
SELECT
  city_month.city,
  city_month.year,
  city_month.month,
  ROUND(city_month.month_avg, 1) AS month_avg,
  ROUND(city_overall.overall_avg, 1) AS overall_avg
FROM city_month
JOIN city_overall
  ON city_month.city = city_overall.city
WHERE city_month.month_avg > city_overall.overall_avg
ORDER BY city_month.city, city_month.year, city_month.month;
