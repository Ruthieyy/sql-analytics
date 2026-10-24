-- Rank cities within each month by average temperature (1 is warmest).
WITH monthly AS (
  SELECT
    year,
    month,
    city,
    AVG(temperature) AS avg_temp
  FROM data_lake.weather_parquet
  GROUP BY year, month, city
)
SELECT
  year,
  month,
  city,
  ROUND(monthly.avg_temp, 1) AS avg_temp,
  RANK() OVER (
    PARTITION BY year, month
    ORDER BY monthly.avg_temp DESC
  ) AS temp_rank
FROM monthly
ORDER BY year, month, temp_rank, city;
