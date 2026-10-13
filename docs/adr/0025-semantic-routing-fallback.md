# ADR 0025 — Resolver semântico como fallback de routing, nunca como router

- Status: aceito (2026-10-07)

## Contexto

O routing determinístico recusa-se a chutar: empate de sinais ou menos de dois
tipos de sinal discriminantes terminam `ambiguous`. Isso é correto — mas deixa
runs sem execução quando a ambiguidade é real e resolúvel por raciocínio (a
intenção favorece um candidato por motivos que os sinais declarados não medem).
A spec do ciclo 3 (Wave K) pede explicitamente: não substituir o router;
adicionar um fallback que recebe só a entrada mínima (task, candidatos
elegíveis, sinais, resumo de tecnologias — nunca o repositório), responde uma
proposta estruturada (`choice`, `confidence`, `reason`, `evidence`,
`alternatives`, `unknowns`) e passa por um validador determinístico.

## Decisão

- **Op `resolve` + flag `resolves_ambiguity`** no manifest: só um provider
  `ready` que declara os dois é candidato a resolver — a escolha entre eles é
  determinística (menor `id`), e `blocked`/`unverified` seguem as portas de
  confiança de sempre.
- **`ResolveRequest/v1` mínimo por construção** (K1): `task`, `candidates` (o
  conjunto que o router já provou elegível, com os sinais que pontuaram),
  `ambiguity` (a razão determinística) e `technologies` (nomes vindos da
  inteligência de projeto — fingerprinted, recomputado quando stale). Nenhum
  arquivo, pack ou conteúdo do workspace sai.
- **`RoutingProposal/v1` é consultiva** (K2): `proposal_selection` revalida a
  escolha — provider registrado, capability resolvida (alias anotado),
  candidato dentro do conjunto oferecido, ação declarada — e a seleção validada
  continua pelo funil inteiro (health, policy, contexto, verificação), como
  qualquer rota determinística. Escolha fora do conjunto, provider desconhecido
  ou ação inventada são rejeições, nunca reparos.
- **Degradação total**: sem resolver declarado, `economy`, falha de transporte,
  `refused`/`error`, `producer` divergente, payload malformado ou escolha
  rejeitada → o desfecho `ambiguous` permanece com a limitação correspondente.
- **Proveniência honesta**: a proposta é persistida (`routing-proposal`, ligada
  ao receipt por `inputs.routing_proposal_sha256`), a decisão gravada carrega a
  razão original da ambiguidade e a marca `semantic resolver`, e a confiança
  fica `low` com `unresolved` declarando que o desempate é raciocínio limitado,
  não sinal medido — raciocínio não é evidência.
- **Backend genérico** (K3): o core conhece só a op e os contratos; hosted
  model, modelo local ou raciocínio provido pelo host são implementações
  intercambiáveis atrás do Forge Protocol.

## Consequências

- O fluxo determinístico não muda: `route()` não conhece o resolver e
  `ambiguous` continua sendo o desfecho quando nada resolve.
- Um `ask` resolvido semanticamente é auditável de ponta a ponta: `routing`
  (decisão final, com a ambiguidade original em `limitations`), `routing-proposal`
  (o que o resolver disse), `telemetry` (span `resolver` + counter
  `semantic_resolver_calls`) e o receipt ligando os hashes.
- Runs anteriores à Wave K são válidos: `routing_proposal_sha256` ausente vale
  "não resolvido semanticamente"; o campo é aditivo em `ReceiptInputs/v1`.
