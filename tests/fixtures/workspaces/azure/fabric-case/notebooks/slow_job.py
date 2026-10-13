big = spark.read.table("lake_sales.Orders")
big.groupBy("customer_sk").count()
big.repartition(1).write.format("delta").save("Files/out")
