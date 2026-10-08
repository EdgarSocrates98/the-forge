# Relatórios

Índice dos relatórios de ciclo e artefatos de evidência. Cada ciclo tem um
relatório principal; waves e auditorias têm documentos próprios.

## Dogfooding (fase corrente)

| Documento | Conteúdo |
|---|---|
| [dogfooding-2026-10-08.md](dogfooding-2026-10-08.md) | Primeira sessão real no próprio repo, seis especialistas: trust deny-by-default, binding de evidência ao vivo, 5 observações (poluição de contexto por basetemp, fronteira do `secrets.scan`, custo de scan) |

## Cycle 5.1 — Ecosystem Expansion Validation

| Documento | Conteúdo |
|---|---|
| [cycle-5.1-ecosystem.md](cycle-5.1-ecosystem.md) | Ecossistema 4→6 especialistas: adapters Azure/Platform, maturidade derivada, B16–B25, onboarding genérico |

Artefato machine-readable: [specialist-reality.json](../reality/specialist-reality.json)
(manifest canônico dos seis especialistas, regenerado por `scripts/reality/collect.py`).

## Cycle 5.1 — Reality Synchronization, Benchmarking & Feature Freeze

| Documento | Conteúdo |
|---|---|
| [cycle-5.1.md](cycle-5.1.md) | Relatório final de fechamento (§102) |
| [cycle-5.1-audit.md](cycle-5.1-audit.md) | Auditoria da Fase 0 + realidade dos especialistas |
| [cycle-5.1-benchmarks.md](cycle-5.1-benchmarks.md) | Suite oficial B01–B15 + hot-paths |
| [cycle-5.1-memory-roi.md](cycle-5.1-memory-roi.md) | Memory ROI medido (on vs. off, bytes, segurança) |
| [cycle-5.1-security.md](cycle-5.1-security.md) | Evidências adversariais §50 + replay suite §29 |
| [cycle-5.1-operational.md](cycle-5.1-operational.md) | Auditoria de docs/contratos, package build, exit codes |
| [cycle-5.1-scorecard.md](cycle-5.1-scorecard.md) | Scorecard de readiness 1.0 (§74–75) |

Artefatos machine-readable:
[cycle-5.1-evidence.json](cycle-5.1-evidence.json) (manifest de evidência §68),
[cycle-5.1-reality.json](cycle-5.1-reality.json) (snapshot datado do
[manifest canônico](../reality/specialist-reality.json)),
[cycle-5.1-scenarios.json](cycle-5.1-scenarios.json) (resultado B01–B15),
[cycle-5.1-hotpaths.json](cycle-5.1-hotpaths.json) (baseline de hot-paths),
[cycle-5.1-memory-roi.json](cycle-5.1-memory-roi.json) (números do ROI).

## Cycle 5 — Federated Engineering Intelligence & Execution

- [cycle-5.md](cycle-5.md) — relatório final (memory, capability graph v2,
  execution targets, remote trust, StrategyPolicy, trace federado)

## Cycle 4.1 / Cycle 4 — Capability Mesh

- [cycle-4.1.md](cycle-4.1.md) — fechamento 4.1 (Global Stop, trace
  federation, adaptive learning)
- [cycle-4.md](cycle-4.md) — relatório do Cycle 4

## Cycle 3.1 — fechamento e auditoria por wave

- [cycle-3.1.md](cycle-3.1.md) — relatório de fechamento
- Waves: [A](cycle-3.1-audit.md) (auditoria), [B](cycle-3.1-wave-b.md),
  [C](cycle-3.1-wave-c.md), [D](cycle-3.1-wave-d.md), [E](cycle-3.1-wave-e.md),
  [F](cycle-3.1-wave-f.md), [G](cycle-3.1-wave-g.md), [H](cycle-3.1-wave-h.md),
  [I](cycle-3.1-wave-i.md), [J](cycle-3.1-wave-j.md)

## Ciclos anteriores

- [cycle-3.md](cycle-3.md) · [cycle-2.1.md](cycle-2.1.md) ·
  [cycle-2.md](cycle-2.md) · [cycle-2-final.md](cycle-2-final.md)

## Notas

- Relatórios são artefatos datados: refletem o estado no fechamento do ciclo.
  O estado vivo do projeto está no [README](../../README.md), em
  [`docs/versioning.md`](../versioning.md) e no
  [manifest de realidade canônico](../reality/specialist-reality.json).
- Observações de dogfooding seguem a taxonomia de
  [`docs/dogfooding.md`](../dogfooding.md) e podem ser registradas como
  `dogfooding-*.md` neste diretório.
