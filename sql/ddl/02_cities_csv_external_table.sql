-- Lookup table of city, region, and climate zone for the join query.
CREATE EXTERNAL TABLE IF NOT EXISTS data_lake.cities (
  city STRING,
  region STRING,
  climate_zone STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 's3://your-bucket/weather/cities/'
TBLPROPERTIES ('skip.header.line.count'='1');
