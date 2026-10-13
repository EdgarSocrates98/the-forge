# Dogfooding — usando The Forge em projetos reais

Após o Feature Freeze ([feature-freeze.md](feature-freeze.md)) o próximo
estado do projeto é **DOGFOODING** — usar o The Forge de verdade em projetos
reais e coletar evidência, não expandir features.

## Como usar

1. Instale no projeto real: `pip install theforge` (ou editable para dev).
2. `theforge init` no workspace; registre os providers reais
   (`theforge providers add`).
3. Trabalhe normalmente: `ask`/`plan`/`execute`/`explain`/`replay`.
4. Quando algo doer, **registre uma observação** — não abra feature.

## O que coletar (§71)

| sinal | onde olhar |
|---|---|
| failures | `theforge explain <run>` — `result.nodes`, `error_family` |
| friction | passos manuais repetidos, flags confusas, mensagens ruins |
| latency | `RunTelemetry`, hot-paths em `docs/performance.md` |
| memory value | `memory_pack` entregou entries úteis? (`pack_stats`) |
| planning quality | plano era certo na primeira? teve que refazer? |
| compatibility drift | `record --check` dos adapters, reality manifest |
| provider behavior | health, limitations declaradas, recusas |
| verification quality | `verified_by` executou de fato? verdict correto? |
| economy | `ContextROI`, bytes entregues vs economizados |

## Taxonomia de observações (§72)

Cada nota de dogfooding recebe um tipo:

```text
bug                    — comportamento errado comprovável
friction               — UX/CLI/docs que atrapalham sem estar erradas
missing capability     — capability que um provider deveria declarar e não declara
bad plan               — plano determinístico/semântico que escolheu mal
unnecessary capability — capability roteada que não devia
slow path              — hot path que regrediu ou latência inesperada
bad memory retrieval   — memory_pack entregou entry irrelevante/stale
bad graph relation     — aresta declarada que induz plano errado
verification failure   — verified_by falhou ou verification_required foi contornado
compatibility drift    — surface de especialista mudou sem version bump
unexpected cost        — bytes/tokens/latência acima do declarado
documentation gap      — doc que promete o que o código não faz, ou omite o que faz
```

Formato sugerido (uma nota por bloco, em issue ou `docs/reports/dogfooding-*`):

```text
type: <taxonomia>
context: comando / workspace / providers envolvidos
expected: o que deveria acontecer
observed: o que aconteceu
evidence: run_id, receipt, log, screenshot
severity: blocker | friction | note
```

## Regra de ouro

**Observação não é feature.** Durante o freeze, um tipo de problema precisa
aparecer repetidamente nas notas (ou ser requisito de segurança/
compatibilidade, ou blocker crítico de usabilidade) antes de virar feature —
o gate está em [feature-freeze.md](feature-freeze.md#feature-request-gate-73).
