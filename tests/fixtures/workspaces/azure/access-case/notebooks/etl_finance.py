"""Daily finance ETL: reads lake, writes UC table."""
from pyspark.sql import functions as F

def run(spark):
    df = spark.read.load("abfss://lake@stg.dfs.core.windows.net/finance/orders")
    cur = spark.table("prod.finance.orders")
    out = df.join(cur, "id", "left_anti")
    out.write.saveAsTable("prod.finance.orders")
    spark.sql("MERGE INTO prod.finance.ledger t USING prod.finance.orders s ON t.id=s.id WHEN MATCHED THEN UPDATE SET *")
