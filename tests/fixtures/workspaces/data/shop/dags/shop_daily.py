from airflow import DAG
from airflow.operators.empty import EmptyOperator

with DAG("shop_daily", schedule="@daily"):
    EmptyOperator(task_id="build")
