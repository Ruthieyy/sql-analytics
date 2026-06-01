-- 创建数据库
CREATE DATABASE data_lake;

-- 创建表（指向S3）
CREATE EXTERNAL TABLE data_lake.weather (
    date STRING,
    city STRING,
    temperature INT,
    humidity INT,
    air_quality INT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
LOCATION 's3://yu-data-lake-test/weather/'
TBLPROPERTIES ('skip.header.line.count'='1');

-- 查询1：每个城市平均温度
SELECT city, AVG(temperature) as avg_temp
FROM data_lake.weather
GROUP BY city
ORDER BY avg_temp DESC;

-- 查询2：空气质量差的天
SELECT date, city, air_quality
FROM data_lake.weather
WHERE air_quality > 100
ORDER BY air_quality DESC;

-- 查询3：每个城市最高温度
SELECT city, MAX(temperature) as max_temp
FROM data_lake.weather
GROUP BY city;
