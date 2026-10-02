# ADR 0003 — Python >= 3.11, stdlib-only em runtime

- Status: aceito (2026-10-02)

## Decisão
O core usa argparse, dataclasses, tomllib e subprocess. pydantic, typer e rich ficam de fora.

## Motivo
Startup rápido, instalação offline, superfície de supply chain mínima. 3.11 traz `tomllib` e `datetime.UTC`.

## Consequências
A validação é escrita à mão (`contracts.base`). Um teste garante a lista vazia de dependências.
