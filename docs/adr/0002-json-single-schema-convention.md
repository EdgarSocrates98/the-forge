# ADR 0002 — JSON e uma única convenção de schema

- Status: aceito (2026-10-02)

## Contexto
O API Forge mistura três convenções de versão (`version` int, `apiforge/*/v1`, `af-*/1`).

## Decisão
Todo contrato persistido usa `schema: "theforge/<Name>/v1"` e hash sha256 sobre JSON canônico (chaves ordenadas, separadores compactos, UTF-8). `schemas/*.json` é o artefato publicado; as dataclasses são a implementação, com paridade testada.

## Consequências
Um único parser genérico (`from_dict`). Campos desconhecidos são ignorados, o que dá forward-compat dentro do major.
