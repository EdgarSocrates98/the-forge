# Forge SDD Contracts — federação (Onda 5)

Contratos versionados entre as Forjas com motor SDD (platform-forge,
api-forge, spark-forge-azure, spark-forge-aws). Não fundem motores: cada
Forja mantém suas fases, perfis, validadores e política de aplicação. O que
a camada comum fixa é **forma, proveniência e semântica dos artefatos de
fronteira** — o suficiente para um consumidor federado ler estados,
evidências, gates e recibos de qualquer Forja sem conhecer seu motor.

Fonte canônica: `the-forge/docs/portable-installation/schemas/Forge*.schema.json`
(mesmo diretório dos schemas `forge/context/v1` — segue o precedente de
ownership do contrato compartilhado de instalação). Distribuição: vendoring
ou leitura de workspace; **nenhum pacote novo obrigatório**.

## Contratos

| schema | papel | produtor típico |
|---|---|---|
| `forge/DecisionTree/v1` | decisões da fase explore (id, tipo, depends_on DAG, status, alternativas c/ recomendação+justificativa, evidência, resposta, ator, impacto, reopen_condition) | engine SDD da Forja |
| `forge/Requirement/v1` | requisitos define (id estável REQ/NFR/US/AC-NNN, kind, acceptance testável, source, decision_refs, critical, status) | define |
| `forge/Constitution/v1` | princípios inegociáveis da Forja/feature (id, text, source, supersedes) | repo ou feature |
| `forge/TaskGraph/v1` | tarefas do plan (T-NNN, depends_on DAG, parallel_safe, risk, write_scope, proof, blocking, requirement_refs, status) | plan |
| `forge/Evidence/v1` | evidência endereçável (kind, path, sha256, produced_by{agent,command}, covers, verdict) | qualquer fase |
| `forge/SDDGate/v1` | resultado de gate (ok, refused[]+unlock, unresolved[]+unlock — mesmo shape dos gates nativos) | check |
| `forge/Convergence/v1` | análise pré-ship (compared[], divergences[] class: missing|partial|contradicts|unrequested|unverified|stale, ok) | converge |
| `forge/SDDReceipt/v1` | recibo de fase (action, actor, inputs_sha256, outputs, verdict, override{reason,actor,undispensable}, rollback_ref) | stamp/ship |

## Regras

1. **Aditivo**: os contratos descrevem artefatos de fronteira; campos
   ausentes significam "não declarado" — nunca inventado.
2. **Sem import cruzado**: cada Forja converte seu formato nativo para o
   contrato no seu próprio adapter (`*/sdd/federated.py`). Nenhuma Forja
   importa o motor SDD de outra.
3. **Gate shape preservado**: `refused`/`unresolved` usam a mesma forma
   `{code, feature, path, field, unlock}` dos motores nativos — um
   consumidor lê qualquer gate sem switch por Forja.
4. **Compatibilidade retroativa**: engines sem `converge`/`decisions`
   emitem apenas os contratos que produzem; consumidor trata ausência.
5. **Sem dependência circular**: contratos são documentos JSON Schema
   (dados), nunca código compartilhado executado por dois motores.
6. **Overrides auditáveis**: `SDDReceipt.override` exige reason+actor;
   `undispensable` marca gates que não admitem dispensa.

## Versionamento

`v1` na string `$id`/schema. Mudança incompatível ⇒ novo `$id` (`/v2`),
nunca edição silenciosa do documento — mesma política do `forge/context`.
