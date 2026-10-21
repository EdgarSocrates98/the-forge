# Delegação governada — SpecialistDelegation + EvidenceHandoff (lf-0028)

Fecha os gaps auditados (forge-cli `docs/integration/confirmed-gaps.md`) em
torno de delegação cross-specialist: declaração, prevenção de ciclos,
handoff de evidência, enforcement de risco/política, bounds e redação,
roteamento determinístico por capability e semântica explícita de recusa.

Três peças, todas em `src/theforge/`:

- `contracts/specialist_delegation.py` — `theforge/SpecialistDelegation/v1`;
- `delegation_governance.py` — gates, cadeia, retry, higiene argv/refs e
  do envelope de evidência;
- `delegation_router.py` — `plan_delegation`, seleção determinística.

**Mapeamento de namespace.** A spec cross-forge nomeia os contratos
`forge/SpecialistDelegation/v1` e `forge/EvidenceHandoff/v1`. Como em
`SpecialistCapability/v1` (lf-0027), dentro do the-forge eles vivem no
namespace `theforge/<Name>/v1`; schemas pinados, gerados em
`schemas/SpecialistDelegation.schema.json` e `schemas/EvidenceHandoff.schema.json`.

**Não confundir.** `theforge/Handoff/v1` (`contracts/handoff.py`) continua
sendo o bus de evidência *entre nós de um plano*. `EvidenceHandoff/v1` é o
envelope *specialist↔specialist*. A execução argv continua em
`delegation.py` + `protocol/transport.py` (sem shell, env higienizado,
caps de saída, kill de árvore de processo); este módulo decide *se* e *como*
a delegação pode ocorrer — nenhum caminho novo executa providers.

## `theforge/SpecialistDelegation/v1`

Declaração do consumer: `consumer`, `specialists[]` (cada um opcional, com
`provider` + `intents[]` declaradas), `policy{discovery,
execution: governed|forbidden, preserve_evidence, fallback}` e `chain`
opcional com o estado de controle da cadeia em voo: `correlation_id`,
`delegation_depth`, `visited_providers[]`, `max_hops`,
`timeout_budget_s`, `cancellation_token`, `cancelled`.

Prevenção de ciclo é estrutural: `visited_providers` é conjunto de ids
únicos cujo primeiro elemento é a origem da cadeia; `|visited| =
depth + 1`. `delegation_governance.admit_hop` recusa provedor já visitado
com `cycle-detected` e orçamento esgotado com `budget-exhausted` —
Sentinel → Spark → Sentinel morre na admissão, nunca executa.

## `theforge/EvidenceHandoff/v1`

Envelope de evidência com `run_id`, `correlation_id`,
`idempotency_key`, `(source_provider, source_version)` →
`(consumer_provider, capability@version)`, `input_refs[]`/`result_refs[]`
(path seguro, ref opaco ou *summary bounded* — nunca log inteiro),
`findings[]` (`id`, `severity`, `confidence`, `summary`, `evidence_refs`),
`limitations`, `error` nomeado, `timestamps`, `resources` e `integrity`.

Vocabulário de confiança fechado: `POSSIBLE | LIKELY | CONFIRMED | UNKNOWN`.
`POSSIBLE` **nunca** é promovido automaticamente. Todo o documento é DATA —
não existe campo de instrução e um finding que lê como ordem continua sendo
uma string sem autoridade (regra data-only, testada).

Bounds na construção: `MAX_REF_VALUE`, `MAX_SUMMARY_CHARS`,
`MAX_HANDOFF_REFS/FINDINGS/LIMITATIONS`, `MAX_EVIDENCE_BYTES` canônicos.
`delegation_governance.bound_handoff` recebe o dict bruto do provider,
clipa texto, poda coleções (findings por severidade), marca
`truncated`/`dropped`, invalida o selo — e **nunca repara** dado
estruturalmente inválido (falha `failed` sem `error` continua erro).

## Roteamento determinístico

`plan_delegation(intent, delegation, discovered)` → plano justificado com
status `planned | ambiguous | unavailable | refused`:

- elegibilidade = declarado ∩ `VERIFIED` ∩ não-visitado; cada exclusão vira
  `DelegationRefusal` com código nomeado (`provider-absent`,
  `version-incompatible`, `permission-denied`, `capability-absent`,
  `cycle-detected`);
- match por conjunto de tokens sobre intents declaradas e id/descrição de
  capabilities — sem LLM;
- empate ou disputa por intent → `ambiguous`/`insufficient-evidence`,
  nunca chute; nunca fan-out para todos os declarados;
- cada pick carrega `justification` (intents servidas, evidência de match,
  resultado do risk gate, versão/estado);
- status honesto: códigos de ausência (`provider-absent`,
  `version-incompatible`, `capability-absent`, `insufficient-evidence`)
  → `unavailable`; códigos de negação (`permission-denied`,
  `policy-refusal`, `cycle-detected`, `budget-exhausted`, `cancelled`)
  → `refused`. Ausência nunca é fantasiada de recusa nem vice-versa.

## Governança

`DelegationRisk`: `LOCAL_READ | LOCAL_WRITE | EXTERNAL_READ |
EXTERNAL_WRITE | DESTRUCTIVE | COST_BEARING`, derivado do
`DeclaredCapability` (`risk`, `network`, `external_cost`, `permissions`).
`LOCAL_READ` passa por default; os demais exigem autorização explícita —
negação vira `policy-refusal`, preservada como recusa, nunca sucesso.

`DelegationFailure` (taxonomia fechada): `provider-absent`,
`version-incompatible`, `capability-absent`, `invalid-input`,
`permission-denied`, `timeout`, `runtime-error`, `invalid-output`,
`insufficient-evidence`, `policy-refusal`, `cycle-detected`,
`budget-exhausted`, `cancelled`. `may_retry` permite retry controlado
**só** para `LOCAL_READ` com falha `timeout`/`runtime-error` dentro do
`ExecutionBudget` (hops, providers, wall-clock injetado pelo chamador).

Higiene: `resolve_capability_argv` valida argv tipado e placeholders
(`{cli}`, `{target}`, `{input}`), rejeitando injeção; refs rejeitam
traversal (`security.paths`); `idempotency_key` = hash canônico de
`(source, capability, run, fingerprint dos inputs)` para dedup de replay;
`seal_handoff`/`verify_integrity` amarram o documento; `redact_handoff`
passa todo free-text por `security.redact` e marca `redacted=True`.
