"""PySpark job of the cross proof workspace: builds the daily orders dataset that the
orders API serves (cross-forge-foundation)."""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("daily-orders-export").getOrCreate()

orders = spark.read.parquet("s3://example-lake/raw/orders/")
items = spark.read.parquet("s3://example-lake/raw/order_items/")

daily_orders = (
    orders.join(items, "order_id")
    .groupBy("order_id", "customer_id", "order_date")
    .agg(F.sum(F.col("quantity") * F.col("unit_price")).alias("total"))
)

daily_orders.write.mode("overwrite").partitionBy("order_date").parquet(
    "s3://example-lake/serving/daily_orders/"
)
