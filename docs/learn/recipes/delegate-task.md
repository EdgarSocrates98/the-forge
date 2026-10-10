# Receita — delegar um intent ao especialista certo

**O quê:** `forge task plan|run` transforma linguagem natural em argv real
executado por uma forja irmã.
**Por que:** você descreve o problema; o roteador determinístico escolhe.
**Quando:** a forja certa existe no workspace e o intent é delegável.
**Quando não:** automação cega em CI sem revisão do plano — rode `plan`
primeiro e exija `--provider`/`--workflow` quando a nota disser `ambiguous`.

## Problema

"Quero analisar meus scripts PySpark sem saber qual forja faz isso."

## Pré-requisitos

Workspace inicializado (`forge init`), especialista com checkout irmão +
manifesto `forge.agentic.json`.

## Passo a passo

```bash
forge task plan "analyze pyspark" --json          # ver o plano primeiro
forge task run  "analyze pyspark" \
  --provider spark-forge-aws --target <dir> --json # executar
forge task explain <task-id>                       # auditar depois
```

## Saída esperada / interpretação

`stage: COMPLETED` + `exit_code: 0` + `executed_steps` com o argv exato +
`evidence`. `PREPARED` = planejado sem executar. Qualquer outro estágio é
falha real — leia `stderr_tail`.

## Verificação

`forge task explain <task-id>` deve reabrir o mesmo `task_id` com o mesmo
estágio — registro persistido, não re-execução.

## Limitações

Delegação exige checkout no workspace (ver [limitações do guia-mãe](../zero-to-multi-specialist.md#limitações-honestas)).

## Erros comuns

| Sintoma | Causa | Ação |
|---|---|---|
| `no delegable specialists` | nenhum manifesto com workflows no workspace | clone a forja irmã ao lado |
| nota `ambiguous` | >1 workflow elegível | `--workflow <id>` da nota |
| `stage: FAILED` | argv do especialista falhou | `stderr_tail` no resultado |

## Uso por agentes

Tudo acima aceita `--json`; o plano é a fronteira humana — agente propõe
`task plan`, humano aprova `task run`.
