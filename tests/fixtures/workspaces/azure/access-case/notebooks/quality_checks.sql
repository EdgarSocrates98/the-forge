SELECT count(*) FROM prod.finance.orders WHERE amount < 0;
SELECT region, sum(amount) FROM prod.finance.invoices GROUP BY region;
OPTIMIZE prod.finance.orders;
