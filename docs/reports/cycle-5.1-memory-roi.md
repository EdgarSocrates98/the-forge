# Cycle 5.1 — Memory ROI report

Medido por `scripts/bench/run_memory_roi.py` (stdlib-only, determinístico,
offline; corpus fixo de 252 entries: 180 falhas do provider `bench-alpha` +
60 decoys + 12 obsoletas). Artefato: `docs/reports/cycle-5.1-memory-roi.json`.
Rode `python scripts/bench/run_memory_roi.py --out <path>` para reproduzir.

## Pergunta: Engineering Memory ajuda?

### Economia de contexto — **sim, medido**

| Métrica | Valor |
|---|---|
| `memory_off_bytes` (store inteiro inline) | 260 874 |
| `memory_on_bytes` (pack escopado entregue) | 32 457 |
| **contexto economizado** | **228 417 bytes (87.6%)** |

O consumidor com memória não lê o histórico inteiro: `memory_pack` entrega um
recorte bounded por `MemoryQuery(capability, task_family, surface)`.

### Custo de retrieval — honesto

| Medição | Mediana | p90 |
|---|---|---|
| `memory_pack` (scoped, bounded) | ~56 ms | ~62 ms |
| `load_entries` (scan integral) | ~53 ms | ~55 ms |

`memory_pack` custa ~4% a mais que o scan cru — o preço do bound é serializar
o que casa para contar bytes. Como não há índice semântico (§18: retrieval é
lookup estruturado), a latência de pack ≈ scan. O ganho está nos **bytes**
entregues, não em latência. Escala futura (índice) deve ser medida, não
assumida — não é custo hoje porque o store é bounded a 1 MiB.

### Influência em decisão — existe um canal, medido

O único caminho pelo qual memória influencia decisão hoje é **governado**:

```
memory entries → failure_patterns() → experimento → StrategyPolicy
                                                    (aprovação humana)
                                                          ↓
                                              preferred_providers()
```

Medido no bench:

- `preferred_without_memory`: `[]` — sem evidência, sem preferência
  (ausência é neutra, nunca sinal negativo);
- `preferred_with_policy`: `["bench-beta"]` — política bench derivada do
  `FailurePattern` agregado (180 ocorrências, pattern `f418ced6…`) muda a
  ordenação;
- **scope gates hold**: a mesma política aplicada a outra surface ou outra
  task_family devolve `[]` — memória não escapa do escopo medido;
- `decision_changed: true`.

`limitations` do artefato: a `StrategyPolicy` do bench é **artefato de
medição** (`approval_sha256` = zeros, declarado em `limitations`). Em
produção a política exige `promote_experiment` + aprovação humana real —
o bench mede o canal, não falsifica a governança.

### Segurança (§16) — verde

| Propriedade | Resultado |
|---|---|
| Terminal (`stale`/`superseded`) nunca entregue | 12 contadas, 0 entregues |
| Surface desconhecida ⇒ não-fresh | `entries_fresh == 0` com `surface=None` |
| Surface diferente ⇒ não-fresh | idem com `OTHER_SURF` |
| Determinismo | packs idênticos entre repetições |

`pack_stats` é read-only e usa o *mesmo* pipeline de `memory_pack` —
instrumentação, não caminho paralelo.

### O que não é medido — e dizemos isso

- **Qualidade de resultado** (memory-on produz melhor output?): não há
  consumidor de `memory_pack` no runtime hoje — nenhum planner/debate lê
  memória. Reportado como `not_measured`, não estimado.
- **Influência direta**: nenhuma decisão lê memória fora do canal
  `patterns → experiment → policy`. Correto por design (§105: nada muda
  routing sem política promovida por humano), mas significa que o ROI
  real depende de um operador promover experimentos.

## Conclusão

Memory **vale** como camada de economia de contexto + prova de evidência
para experimentos: 87.6% de bytes economizados num corpus realista, custo
de retrieval ≈ scan (~56 ms em 252 entries), influência auditável e
confinada ao canal governado. A promessa pendente é *qualidade*: quando um
consumidor real de `memory_pack` existir (planner pré-execução), medir de
novo — a infraestrutura (`pack_stats` + este bench) já está aqui.
