# Test results

| repository | unit/integration | build/lint/typecheck | result | limitations |
|---|---|---|---|---|
| forge-agent-bridge | 107 targeted passed | CI applicable passed | PASSED | external provider NOT_RUN |
| the-forge | targeted 35 passed, 1 skipped; full suite green | CI applicable passed | PASSED | cloud NOT_RUN |
| forge-portal | 592 unit; 45 E2E, 3 skipped | build, i18n, browser CI passed | PASSED | remote PF session NOT_RUN |
| forge-doctor-api | 1945 passed, 39 skipped | suite green | PASSED | — |
| api-forge | 2025 passed, 4 skipped | suite green | PASSED | — |
| code-atlas-forge | 1663 passed, 21 skipped | suite green | PASSED | — |
| forge-lens | full suite and scale smoke green | suite green | PASSED | — |
| data-sentinel-forge | 1057 passed, 8 skipped | suite green | PASSED | — |
| spark-forge-aws | 15124 passed, 14 skipped, 1 pre-fix failure; targeted fix 78 passed | CI fix passed | PASSED | full suite not rerun after allowlist-only fix |
| spark-forge-azure | 3180 passed, 9 skipped | suite green | PASSED | — |

O failure inicial do Spark AWS era o scanner de facts rejeitando legitimamente
`lab/runtime.py`; a correção foi uma allowlist explícita com justificativa e CI
verde, sem alterar o runtime.
