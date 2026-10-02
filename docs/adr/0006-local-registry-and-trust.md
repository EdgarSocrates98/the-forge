# ADR 0006 — Registry local e trust model

- Status: aceito (2026-10-02)

## Decisão
Fontes: builtin > usuário > projeto; trust só vem do arquivo do usuário; entradas de projeto são sempre `unverified`; `unverified` nunca é executado sem opt-in (`--allow-unverified`). Trust: `builtin|trusted|local|unverified|blocked`. O padrão é `unverified`. `blocked` nunca é executado. `builtin` é reservado. O cache guarda só manifests `ready` de providers não `unverified`, verificados por sha256.

## Consequências
Código de terceiros nunca é tratado como confiável em silêncio, e um repositório não pode se autoconceder trust.
