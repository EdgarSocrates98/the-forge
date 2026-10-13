# ADR 0021 — Verificação independente (`can_verify` + op `verify`)

- Status: aceito (2026-10-05)

## Contexto
O `VerificationResult/v1` separa quatro níveis desde o cross-forge-foundation:
o que o provider diz de si (`self_report`, `provider_evidence`), o que o core
confere sozinho (`forge`) e a opinião de um terceiro (`independent`). Até a
Wave G o quarto nível era estruturalmente impossível: a op `verify` era
reservada e `independent` nascia `not_performed`. As relações `can_verify`
já eram declaráveis e o grafo de capabilities já as desenhava — faltava a
orquestração.

## Decisão

### Independência é identidade, não capability
Um verificador é independente quando tem **identidade distinta do produtor**:
outro `id` de entrada e outro `argv` (o mesmo programa sob outro id não é
independente). Um provider que declara `can_verify` sobre a própria capability
descreve auto-checagem útil para o grafo, mas nunca preenche o nível
`independent`. Candidatos `blocked` ou `unverified` sem `--allow-unverified`
também são recusados, e todo descarte é nomeado no `details` do check.

### Seleção determinística
O verificador é o provider `ready` de menor `id` cujo manifest declara a op
`verify` e uma capability com `relations.can_verify` contendo exatamente
`<producer>/<capability>` do run. Sem candidato, `not_performed` diz por quê.
A seleção é do core, não do provider: nenhum provider escolhe quem o verifica.

### O contrato é mínimo e fechado ao essencial
`VerifyRequest{task, capability, action, run_id, result, handoff?}` carrega só
o que já foi persistido e redigido: a `TaskSpec` e o `ExecutionResult` do run
(plus o handoff recebido, em planos). O verificador não recebe arquivos do
workspace nem o contexto — a verificação é sobre o resultado declarado, não um
re-trabalho gratuito. `VerifyVerdict{status, details, basis}` é a resposta.

### Falha do verificador nunca é veredicto
`refused`/`error` no envelope, `producer` divergente, payload malformado ou
falha de transporte viram `not_performed` — só `passed`/`failed` vindos de um
`VerifyVerdict` bem formado são veredictos. Um `failed` independente demove o
run para `partial` com a limitação `independent verification failed:
<verifier>`, a mesma disciplina do `FORGE-RESULT-ARTIFACT-HASH`.

### Regra epistêmica (G4)
Um veredicto `passed` nunca reescreve o status epistêmico da evidência do
produtor: "o verificador concordou" não é evidência concreta da afirmação.
O veredicto é evidência nova *sobre a verificação* (uma identidade distinta
conferiu o resultado), não evidência nova *das afirmações* — um `inferred`
continua `inferred`, e a única via para elevar um status é a evidência nova
que a regra de `derived_from` já exige. O contrato fecha isso
estruturalmente: `VerifyVerdict` não carrega evidência e nada no caminho do
`verify` muta o `epistemic` do resultado.

### Estratégia do verificador é dele
O core não impõe *como* o verificador julga (re-execução, checagem estática,
schema, revisor especialista): o contrato exige só um veredicto auditável com
`basis` declarando a base. Essa é a porta para as estratégias da spec
(`static checks`, `alternative provider`, `test runner`, `specialist
reviewer`) sem nenhuma mudança de contrato.

## Consequências
- Todo run — `ask` ou nó de plano — que devolveu resultado válido passa pela
  seleção; sem verificador declarado o custo é uma varredura de manifests, zero
  subprocessos.
- Nenhum op novo obrigatório: manifests sem `verify` seguem válidos; sem
  verificador o nível fica `not_performed` com a razão explícita.
- O payload do `verify` é aditivo ao protocolo: providers antigos que recebam
  um `verify` respondem `refused`/`error` e viram `not_performed`.
- `verify` deixa de ser op reservada; `estimate` continua reservada.
