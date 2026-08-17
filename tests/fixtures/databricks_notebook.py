# Databricks notebook source
# MAGIC %md
# MAGIC # Aggregate supplier revenue
# MAGIC
# MAGIC This notebook aggregates the gross revenue for each supplier.
# MAGIC 1. Load the raw orders.
# MAGIC 2. Sum the totals per supplier.

# COMMAND ----------

# The aggregation runs once for each day.
orders = ["order"]

# COMMAND ----------

# MAGIC %sql
# MAGIC select count(*) from orders
