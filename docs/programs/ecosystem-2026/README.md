# Programa ecosystem-2026

Programa dos Cycles 8, 9 e 10 — Release Engineering & Distribution, Forge Lab & Benchmarking, Public Adoption. Fonte de direção: `prompt_evo_cycles.md` (workspace `forjas/`, fora deste repo — não versionado aqui).

Execução via Loop Factory: specs em `factory/specs/` dos repositórios, índice em `factory/specs/PROGRAM-ecosystem-2026.md`. Wave 0 produziu os documentos abaixo.

## Documentos

| Arquivo | Conteúdo |
|---|---|
| `baseline.md` | SHAs, versões, empacotamento e CI dos nove repositórios em 2026-10-15 |
| `dependency-map.md` | Mapa de dependências entre componentes e specs do programa |
| `compatibility-matrix.md` | Matriz inicial de compatibilidade (rascunho — não certificada) |
| `open-gaps.md` | Gaps e bloqueios classificados P0/P1/P2 |
| `linux-acceptance.md` | *(pendente — ver §3 do prompt)* |
| `cycle-8-release-readiness.md` | *(pendente — Wave 1)* |
| `cycle-9-forge-lab.md` | *(pendente — Waves 2–3)* |
| `cycle-10-public-adoption.md` | *(pendente — Waves 4–5)* |
| `benchmarks/` | *(pendente — methodology, scenarios, results, limitations)* |
| `security.md` | *(pendente — cyc8-03)* |
| `e2e-evidence.md` | *(pendente)* |
| `FINAL-PROGRAM-REPORT.md` | *(pendente — Wave 5)* |

## Relatórios anteriores

`docs/homologation/` contém a homologação anterior (histórico, não substituto de verificação — §12 do prompt).

## Regras do programa

- Evidência por conclusão: caminho, comando ou commit.
- Funcionalidade existente ≠ funcionalidade homologada.
- Benchmark com LLM só conta se o provedor real rodou.
- Cycle 10 não publica benchmark não aprovado pelo Cycle 9.
- Sem publicação de pacotes, releases públicas ou merge automático.
