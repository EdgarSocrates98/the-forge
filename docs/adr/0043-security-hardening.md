# ADR 0043 — Security hardening: threat model estendido + assinatura por verificador externo

- Status: aceito (2026-10-07)
- Cycle 4, Wave L — §81-85, §119-122

## Contexto

O ciclo abre três fronteiras novas de dados não confiáveis — registry remoto
(http/a2a/mcp), metadados de discovery e streams de métricas — e pede um
threat model de supply-chain (§81), pesquisa de assinatura (§82),
semântica de hash (§83), estados de publisher (§84), suporte a catálogo
corporativo (§85) e uma suíte adversarial cobrindo negociação, registry,
aprendizado e A2A (§119-122).

## Decisão

1. **Metadado remoto nunca concede trust.** Todo candidato remoto é
   `unverified` por construção; trust continua vindo só do `providers.toml`
   do usuário. Popularidade de registry não é sinal de trust.
2. **Hash prova identidade, não segurança.** `manifest_sha256` e
   `distribution.sha256` vão para `expected_hashes` no plano de instalação;
   divergência aborta o plano. Um hash correto não torna conteúdo seguro.
3. **Assinatura: metadado hoje, verificação por verificador externo depois.**
   Pesquisados Sigstore (cosign + OIDC + Rekor), package-index signatures e
   GitHub artifact attestations. Todos exigem dependências fora do stdlib —
   portanto `SignatureRef` permanece declarativo e o `InstallationPlan`
   reserva o stage `verify`. Nenhuma crypto caseira no core.
4. **Catálogo corporativo = mesmo mecanismo de fontes.** `local-file`
   (air-gapped) ou `http` interno; sem código especial.
5. **História de métricas falha fechado.** Malformado → warning + ignorado;
   contagens impossíveis → `ContractError`; observações conflitantes →
   `conflict` explícito; recomendações de estratégia são `advisory=True`
   por contrato e exigem história `warming`/`mature` com runs verificados.

## Consequências

- `tests/test_adversarial_cycle4.py` fixa os invariantes: §119 (claims
  amplos não falsificam profundidade, features não declaradas não satisfazem,
  offer malformada rejeitada, capabilities duplicadas rejeitadas, limites
  contraditórios → `INCOMPATIBLE`), §120 (registry envenenado, typosquat,
  hash modificado, metadado expirado, manifest malicioso), §121 (história
  envenenada, run único, superfície mudada, fake-success, fake-low-cost) e
  §122 (card malicioso, prompt injection, oversized, identidade forjada,
  artifact não suportado).
- O ciclo de import `negotiation ↔ registry` foi quebrado na fonte
  (`negotiate_all` lazy em `discovery.py`) — qualquer módulo pode importar
  a camada de registry sem ordem mágica.
- Gap registrado: verificação real de `SignatureRef` depende de
  dependências externas e fica para um ciclo futuro como componente
  opcional fora do core.
