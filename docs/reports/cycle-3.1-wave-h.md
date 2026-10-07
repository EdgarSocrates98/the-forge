# Cycle 3.1 — Wave H: modelo de segurança da federação + casos adversariais finais

Escopo: Phases 41 (security model update), 42 (data is not instruction),
43 (supply chain) e 59 (final adversarial cases).

## H.1 — Hardening de referências (Phase 41/59)

Os ponteiros federados (`provider_receipt.ref`, `native_trace.ref`) ganharam
validação de forma no contrato — `check_ref` em `contracts/types.py`:

- forma URI: `<scheme>:<id opaco>`, scheme de 2–31 caracteres (uma letra é
  letra de drive, não namespace), corpo sem espaço;
- schemes reservados rejeitados: `file`, `http`, `https`, `ftp`, `ssh`,
  `data`, `javascript` e os namespaces do core (`theforge`, `forge`);
- corpo sem `\` nem segmento `..`;
- `pattern` propagado aos JSON Schemas publicados (`ExecutionResult`,
  `ExecutionReceipt`, `VerifyRequest`, `ExplainReport` regenerados).

O core nunca resolve refs — são rótulos de drill-down. A validação garante
que um ref malicioso não possa nem **parecer** um caminho local para um
consumidor descuidado.

## H.2 — Ameaças da federação documentadas (Phase 41)

Nova seção em `security.md` mapeando cada ameaça à mitigação existente:
handoff malicioso de Doctor (bounded/redacted/origin construída pelo core),
receipt aninhado adulterado (hash do resultado diverge), ref nativo falso
(check_ref + nunca resolvido), spoof de fingerprint (computado pelo core,
nunca declarado), injeção de graph-ref (refs opacos), falsificação de
proveniência (`handoff-provenance` check), escalação do planner (proposta
não tem campo de budget — o perfil do comando é soberano), relaxação de
policy por payload (campos descartados no parse).

## H.3 — Supply chain (Phase 43)

Documentado o tuplo de identidade registrado por execução: fingerprint do
executável + versão do adapter (manifest) + versão observada do especialista
+ fingerprints de superfície (core-computados) + fingerprint nativo
declarado. Wheel hash não é coletado — indisponível offline pós-instalação,
e o tuplo existente já cobre detecção de adulteração local. Reforçado:
hash é integridade, nunca confiança.

## H.4 — Casos adversariais (Phase 59)

`tests/test_federation_adversarial.py` — 20 testes, todos verdes:

| Caso do Phase 59 | Prova |
|---|---|
| Doctor claim com instrução de routing | Texto cruza verbatim como `claim` de item; nenhum nó extra, plano inalterado — é string num campo capado |
| Bundle com provider forjado | `derived_from` citando item nunca entregue → `handoff-provenance: failed` no `verification` gravado |
| Mesma versão, fingerprint mudou | `revalidate` → `changed`, `surface_fingerprint` novo ≠ antigo |
| Receipt aninhado adulterado | Reescrever `provider_receipt.sha256` no `result` gravado → `verify_run_hashes` reporta divergência |
| Provider diz mais barato que o medido | Dois recibos do mesmo `(provider, run)` com custos divergentes → `conflicts` nomeado + `unresolved`, nunca média |
| Graph-ref fora do namespace | 11 formas hostis (`file://`, `theforge://`, `..`, `C:\`, scheme de 1 letra, espaços) rejeitadas no parse; e2e: resultado inteiro vira `provider_failure` |
| Especialista tenta relaxar policy | Campos `policy`/`trust` no payload são descartados pelo parse — nunca alcançam o avaliador |
| Planner quer mais budget que o global | Proposta semântica com 5 providers > `max` (4) → `rejected` pelo `check_plan`; a proposta não tem campo de budget |

Alavanca nova no fixture provider: `evidence_extra` (itens de evidência
autorados pelo teste — usada para o claim hostil e o `derived_from` forjado).

## Prova

- `test_federation_adversarial.py`: 20 verdes
- Suites tocadas: `test_plan_economy`, `test_contracts_models`,
  `test_adapter_apiforge`, `test_verification` — 293 verdes
- Schemas regenerados; `test_schemas.py` cobre a paridade

## Arquivos

- `src/theforge/contracts/types.py` (`check_ref`, `REF_RE`,
  `FORBIDDEN_REF_SCHEMES`, `REF_LEN_MAX`), `result.py`, `telemetry.py`
- `tests/test_federation_adversarial.py` (novo), `tests/conftest.py`
  (markers), `tests/fixtures/providers/fixture_forge.py` (`evidence_extra`),
  `tests/test_plan_economy.py` (refs com scheme ≥2 letras)
- `schemas/` (4 regenerados), `docs/security.md`,
  `docs/reports/cycle-3.1-wave-h.md`
