# Cycle 5.1 — regressão adversarial / segurança (§25–§31, §41–§50)

Auditoria executada sobre a `main` real + a branch `devin/cycle5-final`. Cada
caso da lista adversarial do ciclo (§50) está mapeado para a evidência de teste
que o cobre — sem claims sem prova.

## §50 — mapa de evidências

| Vetor de ataque | Evidência | Teste(s) |
|---|---|---|
| poisoned memory | linhas corrompidas puladas, nunca fatais; escopo `project` nunca exportável | `test_memory.py::test_corrupt_lines_are_skipped_not_fatal`, `test_export_only_moves_portable_scopes` + cenário B06 |
| fake graph edge | relação para capability ausente é dado declarado, não verdade | `test_adversarial_cycle5.py::test_relation_to_unknown_capability_is_data_not_truth` |
| forged approval | promoção de `StrategyPolicy` exige estado `eligible_for_review` + `approval_sha256` real | `test_adversarial_cycle5.py::test_policy_promotion_needs_real_state_and_hash` |
| surface swap | política de surface antiga vira neutra silenciosa; mesma versão + surface nova ≠ fresh | `test_adversarial_cycle5.py::test_old_surface_policy_is_silent_neutral`, `test_surface_staleness.py` (matriz completa) |
| cross-project leakage | escopo `project`/`workspace` recusado e contado no import | `test_memory.py::test_import_refuses_project_scoped` + cenário B15 |
| fake Agent Card | card é self-declared, trust cap `unverified`, promoção só via política | `test_adversarial_cycle5.py::test_card_cannot_self_promote` + cenário B14 |
| fake remote target | alvo declarado não pode admitir `restricted`; allowlist + health + trust exigidos | `test_adversarial_cycle5.py::test_declared_remote_cannot_carry_restricted`, `test_remote.py::test_deny_by_default_empty_allowlist` + cenário B07 |
| fake remote receipt | tamper em request hash/target/provider/artifacts/verification → violações nomeadas | `test_remote.py::TestReceiptBinding` (6 casos) + cenário B13 |
| replay receipt | binding estrutural por `request_sha256` (task+context+budget+provider+surface+target) — ver §29 | `test_remote_replay.py` (10 casos dedicados) |
| provider trust self-claim | trust de A2A nunca sobe via campo; `org-approved`/`verified` só por política | `test_remote.py::test_a2a_promoted_only_by_policy` |
| artifact substitution | artefato esperado ausente nos `output_hashes` → violação; `verify_run_hashes` no core | `test_remote.py::test_missing_expected_artifact` + `test_remote_replay.py::test_receipt_missing_expected_artifact` |
| stale surface | unknown ≠ fresh; bound evidence com fingerprint divergente é stale | `test_surface_staleness.py` (13 casos) + cenário B04 |
| capability identity collision | ids de capability são `provider/cap` namespaced — dois providers com o mesmo `cap.id` produzem nós distintos | `test_capability_graph.py::test_capability_identity_collision_stays_namespaced` |
| strategy scope escalation | `preferred_providers` vazio fora do escopo exato (capability + surface fingerprint) | `test_adversarial_cycle5.py::test_old_surface_policy_is_silent_neutral` + cenário B10 |
| verification bypass | receipt sem referência de verificação → violação | `test_remote.py::test_no_verification_is_violation`, `test_remote_replay.py::test_receipt_without_verification_reference` |
| early-stop verification bypass | nó `verification_required` nunca é podado pelo Global Stop | `test_plan_cycle5.py` (e2e early-stop) + cenário B09 |
| semantic capability injection | routing/planning só aceitam o que o manifest declara; edges do grafo são dados declarados | `test_adversarial_cycle5.py::test_relation_to_unknown_capability_is_data_not_truth`, `test_plan_flow.py` (undeclared handoff → limitation) |
| memory provenance forgery | `confirmed` sem evidência rejeitado no contrato; `source_refs` forjados não mudam `entry_id` (content-derived) e não elevam epistemic | `test_adversarial_cycle5.py::test_confirmed_without_evidence_rejected` |

## §29 — replay attacks (suíte dedicada)

`tests/test_remote_replay.py` — 10 casos. O binding é estrutural: o contrato não
tem campo `nonce` separado porque `request_sha256` já cobre task + context +
budget + provider + surface + target — qualquer desses divergente torna o
receipt inválido. Forgery do hash não ajuda: quem conhece o hash mas trocou
`target_identity_ref`, `provider` ou os artefatos produz violações nomeadas.

## §27 — invariantes de data classification

| Tentativa | Resultado | Prova |
|---|---|---|
| `unknown` → remote | rejeitado (structural cap no request layer) | `test_remote.py::test_confidential_never_remote` |
| `restricted` → remote-forge | rejeitado (mesmo cap; `data_classes` no target teto `public`/`internal`) | mesmo teste + `test_targets.py::test_remote_cannot_declare_restricted` |
| `restricted` → a2a-agent | rejeitado (cap de A2A é `public` apenas) | `test_remote.py::test_a2a_promoted_only_by_policy` |
| `local`/`isolated` locality → remote | rejeitado na política | `test_remote.py::test_locality_forbids_remote` |

Monotonicidade: ignorar um campo nunca transforma `deny` em `allow` (modelo
in-toto: policies são monotônicas, deny-by-default).

## §30 — transporte remoto: prova negativa

`src/theforge/remote.py` não contém transporte: zero `subprocess`/`socket`/
`urllib`/`ssh`/`http` executor — só política + contratos. A docstring declara
explicitamente que "ssh and run" não existe aqui. SSH runner, HTTP executor
genérico, curl-and-trust, remote shell, distributed executor e "Forge Fleet"
seguem **fora de escopo** — documentados como futuro, não implementados.

## §31–§32 — reality proofs e taxonomia de mocks

A taxonomia pedida pelo ciclo mapeia nos markers existentes (deliberadamente
poucos, em `pyproject.toml`):

| §32 taxonomy | Marker/seção do repo |
|---|---|
| unit | `unit` |
| contract | `contract` |
| fixture replay | `integration` sobre adapters `--replay` (tier `specialist-replay`, [real-providers.md](../real-providers.md)) |
| integration | `integration` + `e2e` |
| reality proof | `real_provider` (tier `specialist-real`, env-gated) |
| remote blocked | cenários B07/B13/B14 + `test_remote*` — remote transport é `REMOTE_BLOCKED` por design |

Fixture replay nunca é chamado de execução real — `docs/real-providers.md`
distingue `specialist-replay` de `specialist-real` e o benchmark de economia
declara `provider_mode` por isso.

## §52–§54 — fronteiras declaradas

- **Counterfactual planning**: `CounterfactualPlanComparison` existe só como
  contrato (`contracts/strategy.py`) + validação de schema — **FOUNDATION_ONLY**,
  sem runtime que produza comparações. Documentado assim; nenhum doc afirma o
  contrário.
- **Provider reputation**: não existe engine; observações (performance,
  failures, verification results) são dados para `failure_patterns`/
  `StrategyPolicy` — nada além.
- **Marketplace**: `registry/sources.py` declara "a marketplace UX on top" como
  someday; ADR 0036 registra ordenação sem métricas de marketplace. Deferido
  explicitamente — nenhum PR deste ciclo toca nisso.
- **Supply chain (§51)**: Sigstore/in-toto/SLSA seguem *future hardening* —
  pesquisa documentada, integração fora do ciclo.
