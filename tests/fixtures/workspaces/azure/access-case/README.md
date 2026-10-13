# access_case — corpus do benchmark TokenSave

Bundle UC/ADLS realista (espelho dos fixtures s01 + objetos extras) usado pelo
benchmark `sparkforge-azure tokensave benchmark --case evals/token_efficient/access_case`.

Caso: job Databricks falha ao acessar `abfss://lake@stg.dfs.core.windows.net/finance/orders`
governado por Unity Catalog — principal `spn-job-1`, location `loc_finance`,
credential `cred_lake`, connector ARM ac1, role assignment no storage `stg`.
