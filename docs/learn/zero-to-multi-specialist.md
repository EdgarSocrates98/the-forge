# The Forge — do zero à execução multi-especialista

Guia de ponta a ponta com **evidência real capturada** (Windows, Python 3.14,
the-forge 0.5.0, 6 adapters + 6 forjas irmãs instaladas). Cada saída abaixo é
trecho de execução de verdade, não mock.

## O que você vai construir

Um workspace `.forge/` onde um intent em linguagem natural vira um plano de
delegação, é executado por um especialista via argv real e produz um
`forge/SpecialistDelegationResult/v1` persistido e explicável.

## Pré-requisitos

- Python ≥ 3.11, Git
- the-forge instalado (`./setup.sh` / `setup.ps1`)
- Pelo menos uma forja irmã com checkout irmão no workspace (aqui: as 6)
- Adapters instalados no mesmo venv (`pip install -e ./adapters/*`)

## Passo 1 — inicializar o workspace

```bash
forge init --root E:/projetos/FORJAS
```

```json
{"created": [".forge/config", ".forge/runs", ".forge/cache",
             ".forge/.gitignore", ".forge/config/providers.toml"],
 "forge_dir": "E:\\projetos\\FORJAS\\.forge"}
```

## Passo 2 — verificar o ambiente

```bash
forge doctor --json
```

Os 7 providers responderam `ready/ok surface:<fp>` — incluindo o `echo-forge`
(builtin, usado para prova do protocolo sem nenhuma forja instalada).

## Passo 3 — o que as forjas declaram

```bash
forge capabilities list --json
```

37 capacidades reais, entre elas `glue.analysis ← spark-forge-aws`,
`api.analyze ← api-forge`, `secrets.scan ← platform-forge`,
`data.scan ← forge-doctor-data`, `api.diagnose ← forge-doctor-api`.

Descoberta por requisito (não por nome):

```bash
forge capabilities discover --capability glue.analysis --json
# → "local_provider": "spark-forge-aws", "local_state": "FULL"
```

## Passo 4 — intent vira plano

```bash
forge task plan "assess glue spark jobs" --root E:/projetos/FORJAS --json
```

```json
{"candidates": [{
   "provider": "spark-forge-aws",
   "mode": "DIRECT_CAPABILITY",
   "command": ["...python.exe", "-c",
     "...from sparkforge_aws.adapters.cli import main; main()",
     "analyze", "pyspark", "--path", "E:\\projetos\\FORJAS"]}],
 "notes": [
   "api-forge: ambiguous — workflows ['analyze','doctor']; disambiguate with --workflow <id>",
   "platform-forge: ambiguous — workflows ['analyze','doctor'] …"]}
```

Leitura honesta do plano:

- O roteador **escolheu** `spark-forge-aws` porque o intent bateu no workflow
  `analyze-pyspark` (seleção contextual determinística — nunca `workflows[0]`).
- Os outros 5 especialistas reportaram **`ambiguous` com os ids elegíveis**
  — ambiguidade nunca vira chute; `--workflow <id>` resolve explicitamente.

## Passo 5 — executar de verdade

Fixture mínimo (`/tmp/etl-fixture/job.py`, um script PySpark de 4 linhas):

```bash
forge task run "analyze pyspark" --provider spark-forge-aws \
  --target /tmp/etl-fixture --root E:/projetos/FORJAS --json
```

```json
{"results": [{
   "provider": "spark-forge-aws",
   "stage": "COMPLETED", "exit_code": 0, "elapsed_ms": 800,
   "schema": "forge/SpecialistDelegationResult/v1",
   "executed_steps": ["… sparkforge_aws.adapters.cli … analyze pyspark --path …/etl-fixture"],
   "evidence": ["exit_code=0", "elapsed_ms=800"],
   "stdout_tail": ["…\"extractor\": \"pyspark_ast@0.1.0\"",
                   "\"artifact_sha256\": \"eec7c3b3…\"…"],
   "task_id": "task-88601326422d"}]}
```

O especialista rodou **fora do processo** (subprocess + argv real), extraiu
fatos AST do PySpark com provenance `sha256`, e o resultado foi persistido.

## Passo 6 — explicar depois

```bash
forge task explain task-88601326422d --root E:/projetos/FORJAS
# task-88601326422d  spark-forge-aws  COMPLETED  DIRECT_CAPABILITY
#   exit=0 elapsed=800ms
```

## O que fica persistido

```text
.forge/runs/<task-id>.json   # resultado verificável
.forge/config/providers.toml # registro local de providers
```

## Limitações honestas

- `task plan` só enxerga workflows de especialistas **com checkout no
  workspace** (manifesto `forge.agentic.json` no root do checkout). Uma forja
  instalada fora do workspace aparece saudável em `providers health` mas não
  entrega workflows de delegação — DISCOVERED vs REGISTERED importam.
- `DIRECT_CAPABILITY` executa argv real: o especialista precisa estar
  importável no ambiente (aqui: path-insert do checkout).
- Delegação fã-out (`--max-parallel`) existe; streaming ao vivo no TUI não.

## Próximos passos

- `forge ask "<pergunta>"` — roteamento por pergunta
- `forge plan` — plano multi-provider com grafo
- `forge explain`/`replay`/`resume` — ciclo de evidência
- Trilhas: [README.md](README.md) · Receitas: [recipes/](recipes/)
