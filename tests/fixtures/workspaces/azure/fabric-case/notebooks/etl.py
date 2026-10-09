df = spark.read.table("lake_sales.Orders")
df2 = spark.read.format("delta").load("Files/ext/orders")
df.join(df2, "order_id").write.mode("overwrite").saveAsTable("lake_sales.Out")
