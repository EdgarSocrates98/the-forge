# ADR 0019 — Taxonomia de erros, reprodutibilidade e replay

- Status: aceito (2026-10-04)

## Contexto
Com planos multi-provider ([ADR 0018](0018-multi-provider-execution.md)), automações passam a depender de três coisas que até a Wave C eram informais. Primeiro, os códigos `FORGE-*` cresceram sem agrupamento, e a CLI mostrava mensagens sem código, às vezes com traceback em erro interno. Segundo, nada dizia se um run podia ser repetido com o mesmo resultado, nem distinguia "mostrar de novo", "conferir de novo" e "executar de novo". Terceiro, o `explain --json` era o despejo dos artefatos, sem versão e sem conferir se o run foi alterado depois de gravado.

## Decisão
### Taxonomia de erros
- Todo código `FORGE-*` pertence a exatamente uma família: `protocol`, `registry`, `routing`, `plan`, `context`, `provider`, `policy`, `persistence`, `security`, `workspace`, `replay`, `usage` ou `internal`. Os códigos de trust ficam em `security`. `routing` não tem códigos: `ambiguous` e `no_route` são desfechos legítimos, não erros.
- Fonte única: valores em `contracts/codes.py` e família em `CODE_FAMILIES`. [errors.md](../errors.md) é a lista canônica; os outros documentos apontam para ela. `tests/test_error_taxonomy.py` falha para código sem família, para divergência entre `errors.md` e o mapeamento, para código citado num documento e ausente de `errors.md`, para tabela que atribui família diferente e para valor publicado alterado (golden em `tests/golden/forge_codes.json`). `tests/test_codes.py` proíbe literais `FORGE-` fora de `codes.py`.
- Códigos nativos de providers (`AF-*`, `SPARKFORGE-*`, `APIFORGE-*`, `ADAPTER-*`) passam intactos, não têm família e são mostrados como `provider code`.
- Todo erro esperado de The Forge carrega um código da taxonomia (`ForgeError.code`): uso `FORGE-USAGE` ou `FORGE-PLAN-FILE`, persistência `FORGE-PERSIST-WRITE`/`-READ`, recusa de replay `FORGE-REPLAY-*`.

### CLI governada, exit 6 e `--debug`
- Toda mensagem de erro mantém o prefixo histórico (`theforge: error:`, `theforge: persistence error:`, `theforge: internal error:`, `theforge: interrupted`) e termina com `[<código> · <família>]`. Nunca há traceback, em texto ou JSON.
- `--debug` (comum a todo subcomando) mostra um `Diagnostic` (`theforge/Diagnostic/v1`) redigido: estágio, código, família, tipo, mensagem, causas e quadros só de módulos `theforge.*`, sem variáveis locais. Num run de `ask`/`plan` com erro interno, ele só é gravado como artefato com `--debug`.
- Os exits existentes não mudam. Entram `planned` → 0, recusa de `replay --mode execute` → 4 (o mesmo de um desfecho recusado) e o novo exit **6** para divergência de integridade (`explain`, `replay --mode verify` e `--mode render`). O conjunto total é o dos desfechos {0, 3, 4} mais os fixos {1, 2, 5, 6, 70, 130}. `FORGE-PERSIST-DIVERGENCE` é o código da taxonomia para essa situação; a saída (texto ou `--json`) lista as divergências e o stderr traz uma única linha governada `theforge: integrity divergence: <n> artifact(s) diverge [FORGE-PERSIST-DIVERGENCE · persistence]`, que classifica a divergência sem alterar o stdout.

### Reprodutibilidade
Todo receipt registra um nível com os motivos:

| Nível | Quando |
|---|---|
| `unknown` | nenhum provider executou (`no_route`, `ambiguous`, recusa antes do `execute`, `planned`) ou o nível não foi gravado (runs anteriores a esta versão) |
| `non_reproducible` | o provider declara rede, execução não local ou não offline; a capability é `external_read`, `external_mutation` ou `destructive`; houve divergência de contexto; ou um handoff veio de um nó `non_reproducible` |
| `reproducible` | todas as condições: execução determinística **declarada** (`execution.deterministic: true`), capability `read_only`, fingerprint do provider e hash de contexto registrados, reverificação de contexto executada (não `minimal`), verificação `forge` aprovada, status `ok` e handoff só de nós `reproducible` |
| `partially_reproducible` | os demais casos, com cada condição não atendida como motivo |

- Determinismo não declarado nunca resulta em `reproducible`.
- Um plano recebe o nível menos reprodutível dos nós, na ordem `non_reproducible` < `unknown` < `partially_reproducible` < `reproducible`. `unknown` fica abaixo de `partially_reproducible` porque não se sabe nada sobre o nó: um plano com um nó `skipped` (sem execução, nível `unknown`) é `unknown`.

### Verificação em quatro níveis
O `VerificationResult` separa o que o provider diz (`self_report`, `provider_evidence`: só `reported`) do que The Forge confere (`forge`: integridade do resultado, `producer`, reverificação de contexto pelo nível do perfil e sha256 de cada artifact em `work/`) e de uma verificação independente (`independent`, sempre `not_performed` enquanto `verify` é reservada). O contrato impede auto-relato marcado como aprovado.

### `explain` versionado e replay
- `explain --json` emite `ExplainReport` (`theforge/ExplainReport/v1`, schema publicado): seções tipadas, `not_recorded` para seções sem dado, relatório de integridade e os artefatos crus em `artifacts.<nome>` (ausentes omitidos). Regra de versão: dentro de v1 só entram campos opcionais com default; remover ou mudar o tipo de um campo exige v2.
- A verificação de hashes recalcula cada hash que o receipt registrou e cada artifact declarado, sem escrever e sem iniciar providers; o receipt é a âncora de confiança.
- `replay` tem três modos distintos: `render` (só artefatos, sem ler o workspace), `verify` (hashes mais reverificação dos itens de contexto contra o workspace atual) e `execute` (novo run com os parâmetros originais, provider fixado e `replay_of`, comparando os resultados sem campos voláteis). `execute` só aceita runs de um provider `reproducible` ou `partially_reproducible`; recusa, antes de iniciar qualquer provider e com todos os motivos, runs de plano ou de nó (`FORGE-REPLAY-UNSUPPORTED`) e runs `non_reproducible`/`unknown`, com entradas registradas divergentes, com contexto alterado no workspace ou com provider de identidade ou versão diferente (`FORGE-REPLAY-NOT-REPRODUCIBLE`).

## Alternativas
- **Famílias derivadas do prefixo do código.** Prefixos históricos não batem com a família (`FORGE-PROVIDER-BLOCKED` é de `security`, `FORGE-RECEIPT-INVALID` é de `persistence`), e renomear códigos publicados quebraria automações. Um mapeamento explícito, testado e congelado resolve sem renomear.
- **Exit distinto por família.** Multiplicaria os exits e quebraria automações que dependem dos atuais. A família vai no texto e no JSON; o exit continua por desfecho, com um único valor novo (6).
- **Traceback com `--verbose`.** Um traceback bruto pode carregar segredos de variáveis e caminhos do usuário. O diagnóstico estruturado e redigido dá a mesma localização sem esse risco.
- **Reprodutibilidade binária.** Esconderia a diferença entre "falta uma declaração" (`partially_reproducible`, ainda reexecutável) e "acessa o mundo externo" (`non_reproducible`).
- **Inferir determinismo pelo comportamento.** Exigiria executar duas vezes e ainda não provaria nada; a declaração explícita do provider é verificável por revisão e nunca é presumida.
- **Re-execute de planos.** Exigiria repetir handoffs e decisões de vários providers de forma coerente; fica fora desta versão e é recusado com código próprio.

## Consequências
- Automações podem tratar erros pela família e pelo código, sem interpretar texto, e ler um `explain --json` versionado e conferido.
- Um run alterado depois de gravado é detectado (exit 6), exceto adulteração coordenada de receipt e artefatos, que exige uma âncora externa ([security.md](../security.md#integridade-de-runs-e-âncora-de-confiança)).
- Nenhum adapter real declara `deterministic` nesta versão, então seus runs ficam `partially_reproducible` no máximo; o eco embutido declara e produz runs `reproducible`.
- Acrescentar um código exige atualizar `codes.py`, `CODE_FAMILIES`, `errors.md` e o golden no mesmo commit. Detalhes de CLI em [cli.md](../cli.md#mensagens-de-erro-e---debug).
