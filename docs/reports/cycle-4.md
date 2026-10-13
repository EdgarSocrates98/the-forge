# Cycle 4 — Capability Mesh: relatório final

Relatório do `prompt_evo_cycle4.md` (Waves A–M). Fonte: execução real do CLI em
subprocesso (`tests/test_reality_proofs.py`) mais a suíte completa. Branch:
`feat/cycle4`. Base: Cycle 3.1 mergeado em `4576662`.

## Waves entregues

| Wave | Escopo | Commit |
|---|---|---|
| 0 | branch `feat/cycle4`, baseline 3.1 verificada | — |
| A | `CapabilityRequirement`/`CapabilityOffer`/resultado — negociação determinística por gates, nunca por score opaco | incluído |
| B | routing por requirement, `--use` pin, `negotiation` aditivo em `RoutingDecision`, plan path | incluído |
| C | abstração de fontes (`local-file`, `http`, …), fonte local autoritativa intacta | `9e7c6c9` |
| D | cliente http read-only: cache hash-verificado, freshness, `THEFORGE_NO_NETWORK` | `521b843` |
| E | discovery por requirement — candidato remoto é metadado, nunca instala | `a9ff17f` |
| F | `InstallationPlan` v2: pinned, `expected_hashes`, gate `--approve`, rollback metadata — plan-only | `9ae4f61` |
| G | `ExecutionObservation`/`GlobalEconomyReceipt` — conflitos preservados, nunca média silenciosa | `b91438e` |
| H | `ShadowRecommendation` advisory-only; frio não aconselha; escopo por surface fingerprint | `a4abf2f` |
| I | bridge A2A experimental — Agent Card → candidato `unverified`; core segue Forge-nativo | `2ecfa74` |
| J | MCP registry awareness — `McpServerEntry` separado de providers; deps declaráveis no manifest | `9a5b0c2` |
| K | auditoria empírica de forge-contracts → decisão documentada de **não extrair** | `987b265` |
| L | threat model supply-chain + suíte adversarial §119-122; assinatura delegada a verificador externo | `85092b4` |
| M | provas de realidade 1-7 + benchmarks + este relatório | esta wave |

## Provas de realidade (§136-142)

Todas em `tests/test_reality_proofs.py`, rodando `python -m theforge` em
subprocesso — nenhum atalho in-process onde existe path de usuário:

1. **Negociação local** — `fixture-spark` (offline) vs `fixture-spark-net`
   (`requires_network`), mesma capability `spark.performance`. Requirement
   `network_allowed=false` → net `INCOMPATIBLE` (`runtime:network_denied`),
   `ask --requirement` seleciona `fixture-spark`. ✅
2. **Capability ausente** — `quantum.optimize` não instalada; fonte
   `local-file` com documento remoto oferecendo-a → `discover` reporta o
   candidato `unverified`/`signature_state=none`, `action_taken=false`, e
   `registry list` continua sem o provider. ✅
3. **Plano de instalação** — `install plan` duas vezes produz planos
   idênticos fora `created_at`/`approved_at`; `--approve` só registra o gate;
   nada instalado em nenhum dos caminhos. ✅
4. **Economia global** — histórico medido favorecendo o challenger gera no
   máximo `ShadowRecommendation` com `advisory=true` e evidência; o provider
   selecionado é sempre um registro instalado real. ✅
5. **Mudança de superfície** — perf entry com fingerprint antigo →
   negociação reporta `history=stale`, nunca reutiliza o score. ✅
6. **A2A** — Agent Card servida em loopback via fonte `kind=a2a` vira
   candidato com provenance (`source=a2a-feed`) e nunca entra no registry de
   providers. ✅
7. **Offline** — `THEFORGE_NO_NETWORK=1`: fonte `http` não é consultada,
   fonte `local-file` continua lendo, `negotiate`/`discover` funcionam. ✅

## Benchmarks (CLI real, subprocesso, workspace de fixture)

| Comando | Latência | Observação |
|---|---|---|
| `capabilities negotiate` | ~1100 ms | inclui startup do Python + describe dos providers |
| `capabilities discover` | ~640 ms | local + fonte local-file |
| `registry list` | ~490 ms | |
| `economy report` | ~470 ms | agrega stream JSONL local |

Todo o custo é processo local — zero rede no caminho padrão.

## Gates locais (CI do GitHub esgotada — suite local é o gate)

`pytest` completo verde · `ruff check` limpo · `mypy src` limpo (171 arquivos)
· schemas regerados · adversarial §119-122 verde · provas §136-142 verdes.

## Decisões de arquitetura registradas

- ADR 0033-0042: waves C–K (sources, remote client, discovery, plan v2,
  observações, shadow, A2A, MCP, contracts-audit).
- ADR 0043: threat model de supply-chain + `SignatureRef` declarativo —
  verificação por verificador externo opcional (Sigstore/índice/attestations
  pesquisados; nenhuma crypto caseira no core stdlib-only).

## O que mudou de verdade

- A fronteira de trust ficou explícita: metadado remoto (registry/A2A/MCP)
  **não pode** criar trust, identidade ou roteabilidade — provado por teste,
  não só documentado.
- O ciclo de import `negotiation ↔ registry` foi eliminado na fonte.
- Métricas envenenadas falham fechado; conflitos econômicos ficam visíveis
  como `conflict`, nunca viram média.
- Descoberta remota é `discover` + `install plan` — nenhum caminho instala ou
  executa candidatos.
