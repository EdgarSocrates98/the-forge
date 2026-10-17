# Cycle 11.2 — Python matrix (P1-004)

Escopo: `requires-python` / classifiers / matriz CI por repo após os 6
PRs mergeados (platform-forge#54, api-forge#84, spark-forge-aws#172,
spark-forge-azure#65, forge-doctor-data#51, forge-doctor-api#64).

## Comandos executados

```text
grep requires-python/classifiers pyproject.toml      # por repo (origin/main)
grep -oE "3\.1[0-9]" .github/workflows/*.yml | sort -u  # legs de CI
gh pr view <n> --json state,mergeCommit               # cada PR
```

## Matriz pós-merge (origin/main auditado)

| Repo | SHA main | requires-python | Classifiers | CI matrix | Piso coberto? |
|---|---|---|---|---|---|
| the-forge | ba660e7 | >=3.11 | 3.11, 3.12 | 3.11–3.14 (ubuntu+windows) | ✅ |
| api-forge | cb13bdb | >=3.12 | 3.12, 3.13, 3.14 | 3.12–3.14 (validate + windows-parity) | ✅ completo |
| platform-forge | 2a9bf44 | >=3.10 | 3.10–3.13 | 3.10–3.13 | ✅ piso; 3.14 dentro do range sem leg — documentado |
| spark-forge-aws | 4a70021 | >=3.10 | 3.10–3.14 | 3.10–3.14 (schedule/dispatch; PR leg em 3.11) | ✅ completo |
| spark-forge-azure | 3ed7e75 | >=3.10 | 3.10–3.14 | 3.10–3.14 (ubuntu+windows `full`) | ✅ completo |
| forge-doctor-data | 3f2fe0e | >=3.11 | 3, 3.11–3.13 | 3.11–3.13 | ✅; 3.14 dentro do range sem leg — documentado |
| forge-doctor-api | beb0e08 | >=3.11 | 3.11–3.13 | 3.11–3.13 | ✅; idem 3.14 |

Notas de drift ciclo-11.1→11.2: spark-azure ganhou 3.11/3.13/3.14 (antes
sem 3.11/3.13); spark-aws ganhou 3.13/3.14; api-forge ganhou 3.13/3.14
(antes só 3.12); platform ganhou classifier 3.13 (CI já cobria).
Gaps residuais declarados (não escondidos): 3.14 sem leg em
platform-forge e nos dois doctors — registrado nos patch plans como
candidato do próximo ciclo.

## Evidência local (de cada patch-plan)

Locks gerados por `scripts/gen_lock.py` (spark-aws: `locks/py3.13.txt` +
`py3.14.txt`, `test_supply_chain.py` exige paridade lock↔matrix).
Smoke local em uv-managed 3.10.21/3.11.16/3.13.15/3.14.7 — wheel builds e
`--help`/`--version` verdes onde declarado (`docs/releasing/
pypi-patch-plan.md` por repo). `Blockers: None` nos 6.

## Veredito

VERIFIED — todo `requires-python` tem piso coberto por CI e
classifiers alinhados à realidade testada; cobertura intermediária agora
completa em api-forge/spark-aws/spark-azure, parcial documentada em
platform/doctors (3.14).

## Risco residual

Legs 3.13/3.14 em schedule/dispatch (spark-aws) — a quebra só aparece no
nightly, não no PR. Locks de 3.13/3.14 gerados em `x86_64-manylinux_2_28`
— macOS/Windows wheels dependem da resolução normal de deps.
