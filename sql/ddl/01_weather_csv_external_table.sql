-- Landing table for the raw daily weather CSV in S3.
CREATE EXTERNAL TABLE IF NOT EXISTS data_lake.weather (
  date STRING,
  city STRING,
  temperature INT,
  humidity INT,
  air_quality INT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 's3://your-bucket/weather/raw/'
TBLPROPERTIES ('skip.header.line.count'='1');
