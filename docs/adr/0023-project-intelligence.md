# ADR 0023 — Inteligência de projeto: freshness computada, reuso por seção

- Status: aceito (2026-10-05)

## Contexto

O ciclo 3 pede memória técnica incremental: a descrição do workspace
(repositórios, tecnologias, relações) não deveria ser recomputada inteira a cada
plano, e o sistema não deveria esquecer as decisões que já provou. O risco
clássico de qualquer cache: devolver dados velhos como se fossem atuais —
"never stale silently" é o requisito, não o desejo.

## Decisão

### Freshness é veredito de leitura, nunca campo gravado
`ProjectIntel/v1` carrega fingerprints, fonte e timestamps — e **não** carrega
`validity`. Um `current` persistido apodrece na hora em que o workspace muda;
a forma honesta é recomputar os digests na leitura e responder `current`,
`stale` (com as seções nomeadas) ou `unknown` quando nem isso se consegue. O
documento guarda a *evidência* da atualidade; quem lê decide.

### Reuso por seção, não por documento
O fingerprint é composto: `files`, `repos`, `depfiles`, `manifests`,
`relations`. Cada seção do descriptor declara de quais inputs deriva; o refresh
reusa verbatim só o que ainda bate (`technologies`, `dependency_files`) e
recomputa o resto. Descoberta de repositórios é barata e roda sempre; o estado
git é evidência viva — nunca servido do snapshot, mesmo quando tudo mais bate.

### Memória de decisões é só o reutilizável
`DecisionMemory/v1` guarda quatro tipos — routing, profile, pattern, verdict —
com a `basis` registrada. Deduplicação por `sha256(kind|subject|choice)`:
repetir a decisão reafirma a entrada, não a duplica. Cap de 256 entradas e
trilha de 16 runs. A memória **informa** (`theforge decisions`); nunca roteia
sozinha — decisões novas passam pelo routing determinístico de sempre.

## Consequências

- Nada persistido pode mentir sobre atualidade: a pior resposta é `unknown`.
- O reuse é auditável: `intel.reused` e a limitação do run dizem o que veio do
  snapshot; o artifact `workspace-descriptor` do run continua sendo o que o run
  viu de fato.
- Uma seção cujo fingerprint não pode ser verificado é `stale` — nunca
  presumida atual.
