# Agentic Ecosystem — Polish & Closure Report (prompt_evo_agentic_ecosystem §50)

**Verdict:** AGENTIC_POLISH_COMPLETE_REMOTE_BLOCKED

Fase de consistência, não de features: código, documentação, agentic assets,
benchmarks e reality evidence agora descrevem o mesmo sistema. SHA
`validated_source_sha` registra o código validado; o commit que contém este
documento é posterior por construção (§64 — nenhum arquivo carrega o hash do
commit que o contém).

## Repository State

```text
validated_source_sha  28016c72a9c5917abe131b7a517fb43e2287d634
forge_version         0.5.0 (bump decidido nesta fase, §30-34)
python                CPython 3.11.15
os                    Windows-10-10.0.26300-SP0 (AMD64, 6 cpus)
tests                 4684 collected · 4629 default selection verde
                      (55 deselected: slow + real_provider, rodados à parte)
contracts             48 módulos em src/theforge/contracts/
schemas               69 JSON schemas (python -m theforge.contracts.schema)
```

## Agentic Assets

```text
canonical Forge skills   16  (agentic/skills/*.md → 3 hosts, --check em sync)
Kiro skills              17  (mirrors nos 3 hosts, paridade semântica)
AgentSpecs                8  (agentic/agents/*.toml, AgentSpec/v1)
Codex rendered agents     9  (8 specs + spec-reviewer host-native)
specialists               6  (sparkforge-aws/azure, apiforge, platformforge,
                              doctor-data, doctor-api)
adapters                  6  (adapters/*)
```

## Specialist Reality

Regerado por `scripts/reality/collect.py` em `docs/reality/specialist-reality.json`
(forge.commit_sha = 4ed7e2e3, bump 0.5.0). Checkout divergence e surface drift
são colunas separadas por desenho (§27).

| Specialist | SHA | Origin Main | Surface | Maturity | Status |
|---|---|---|---|---|---|
| spark-forge-aws | 828827d7 | diverged | none | VERIFICATION_READY | snapshot_fresh_install_diverged |
| spark-forge-azure | c09d4c5c | same | none | EXECUTION_READY | fresh |
| api-forge | 1745f872 | diverged | none | VERIFICATION_READY | snapshot_fresh_install_diverged |
| platform-forge | 0aee5c6f | same | none | EXECUTION_READY | fresh |
| forge-doctor-data | 3a8d7a56 | same | none | EXECUTION_READY | fresh |
| forge-doctor-api | 035b6358 | diverged | none | EXECUTION_READY | snapshot_fresh_install_diverged |

Maturidade derivada de evidência (`EXPECTED_LEVEL` em
`test_federation_conformance.py` — asserção, não declaração): doctors
verificam AWS e api-forge; azure/platform/doctors seguem em EXECUTION_READY
porque ainda não há verificador na federação para as capabilities deles — não
foram elevados artificialmente (§29).

## Skills

16 canônicas, renderizadas em paridade nos 3 hosts (`render_skills.py --check`
em sync, `audit_assets.py` sem findings). Comandos `theforge` citados em skill
resolvem contra o parser real (`test_all_skills_quote_only_real_cli_verbs`).

## Agents

Os 8 AgentSpecs reais — autoridade fechada, `UNIVERSAL_FORBIDDEN` construtivo
(approve/grant-trust/waive-verification/modify-registry impossível de
declarar). Regressões §57-62 cobertas por `test_agentic_security.py` +
`test_agent_registry.py`.

| Agent | Authority | Rendered |
|---|---|---|
| ecosystem-router | propose | codex |
| forge-discovery | classify | codex |
| capability-negotiator | propose | codex |
| bootstrap-installation | execute-approved | codex |
| cross-forge-planner | propose | codex |
| execution-orchestrator | execute-approved | codex |
| verification-orchestrator | propose | codex |
| ecosystem-debugger | advise | codex |

## Benchmarks

A01–A15 reexecutados em worktree limpa (`docs/reports/agentic-scenarios.json`,
commit 9b812d8, `git_dirty=false`, forge 0.5.0): **15/15 pass**.

```text
requests                    11
deterministic_resolved       8
agentic_fallback_needed      3
agentic_accepted             1
agentic_rejected             2
unnecessary_invocations      0
```

Invariantes §18 mantidos: routing determinístico dominante, zero invocações
desnecessárias, picks fora do offered set rejeitados. `specialist_shas`
populado com os seis SHAs reais (o helper lia a chave errada do manifest —
corrigido nesta fase).

## Security

Suíte adversarial agentic verde: authority walls construtivos, plano de
instalação staged+aprovado, `latest` recusado, injection de provider/resolver
rejeitada, evidência re-vinculada ao sha256 estagiado, knowledge estático
nunca verdade de runtime (§57-62).

## Local Gates

| Gate | Status |
|---|---|
| pytest (default) | green — 4629/4629 |
| pytest -m slow | green |
| pytest -m security | green |
| pytest -m real_provider | green — 51/51 (6 venvs reais) |
| ruff check . | green |
| ruff format --check . | green (11 arquivos formatados nesta fase) |
| mypy src | green — 150 arquivos |
| schema parity | green (regen sem diff) |
| agentic audit | green — 0 failing findings |
| skill render check | green — 16 em sync ×3 hosts |
| agent render check | green — 8 em sync |
| compat matrix | green — 0.5.0 tem linha; matriz estendida aos 6 adapters |
| package build | green — sdist + wheel 0.5.0 |
| CLI smoke | green — help/knowledge/agents (human + JSON) |

## CI

```text
LOCAL_GREEN
REMOTE_BLOCKED   (GitHub Actions quota esgotada — jobs sobem sem steps;
                  autorizado a ignorar, não é falha de código)
```

## Known Limitations

- **Remote execution**: política/recibos testados (B07/B13); nenhum
  transporte remoto conectado — diferido por design.
- **Resolver**: nenhum adapter real declara `resolve`; proposta→validação
  exercida por pure functions, não por resolver live.
- **A-series**: usa fixtures de replay (`tests/fixtures/native`), não
  execução live — declarado em `evidence_note` do artifact.
- **`echo-forge`**: provider de teste presente no registry local (2 caps);
  os 35 capabilities documentados referem-se aos seis especialistas reais.
- **CI remota**: indisponível por quota — evidência local máxima.

## Versioning

`0.5.0` — minor release aprovada: superfícies públicas novas desde 0.4.0
(ForgeKnowledge/v1, AgentSpec/v1, verbos `knowledge`/`agents`, skills
canônicas, registry de agentes). Matriz de compatibilidade de
`docs/versioning.md` ganhou linha 0.5.0 e colunas dos dois adapters do ciclo
5.1 — estava 4/6 antes desta fase.

## Final Verdict

```text
AGENTIC_POLISH_COMPLETE_REMOTE_BLOCKED
```

Gaps fechados: report stale → regenerado com os 8 AgentSpecs reais; contagem
de skills → 16 em todo doc vivo (e lista de nomes inexistentes removida);
benchmark → re-executado clean-tree com SHAs reais; reality manifest →
regenerado na versão correta; versionamento → decidido (0.5.0) e consistente
em 7 superfícies; docs ↔ código → consistente; gates locais → verdes.
