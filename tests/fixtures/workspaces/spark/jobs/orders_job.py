"""Tiny PySpark job used as an example workspace for the Spark Forge adapter."""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType

spark = SparkSession.builder.appName("orders-daily").getOrCreate()

orders = spark.read.parquet("s3://example-bucket/raw/orders/")
customers = spark.read.parquet("s3://example-bucket/raw/customers/")


@udf(returnType=StringType())
def normalize_status(status):
    return (status or "").strip().lower()


daily = (
    orders.join(customers, "customer_id")
    .withColumn("status", normalize_status(F.col("status")))
    .groupBy("order_date", "status")
    .agg(F.sum("total").alias("revenue"))
)

print(daily.collect())
daily.repartition(1).write.mode("overwrite").parquet("s3://example-bucket/curated/orders_daily/")
