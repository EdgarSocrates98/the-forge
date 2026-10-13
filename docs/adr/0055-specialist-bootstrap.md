# ADR 0055 — Specialist bootstrap: conhecimento → plano → aprovação → verificação

- Status: aceito (2026-10-08)

## Contexto

Quando uma tarefa precisa de um especialista que não está instalado (§90:
`no_route` → install plan), a plataforma precisa de um caminho governado —
não um `pip install` improvisado. O fluxo tem que ser auditável, reproduzível
e separar quem instala de quem verifica.

## Decisão

O bootstrap é um pipeline de artefatos, não uma ação:

1. **Conhecimento** (`forge-knowledge/<id>.json`) diz *como* instalar —
  `install[]` com comandos reais documentados, `python` constraints,
  `verify_install`, `discover_command`.
2. **Plano** (`plan_installation`, `InstallationPlanV2`) transforma a
  entrada do registry em estágios `pending`: fetch → verify hash → install
  → verify install → discover → register. `'latest'` nem chega aqui — o
  `ForgeRegistryEntry` rejeita versão não-SemVer na construção.
3. **Aprovação** é gate humano/policy: `plan.approval.required` —
  `bootstrap-installation` executa somente com evidência de aprovação, e
  nunca pode produzi-la (UNIVERSAL_FORBIDDEN).
4. **Verificação independente**: `verify_install` + `discover` rodam o
  binário real; quem instalou (`install` allowed) tem `verify` forbidden —
  o relatório de saúde vem do especialista, não do instalador.
5. **Runtime reality vence**: depois de instalado, capabilities/health/
  surface vêm do `describe` ao vivo — o pacote de conhecimento volta a ser
  apenas bootstrap metadata.

Não há auto-upgrade (§58): `tested_version` é "o que foi medido"; instalar
versão nova é um plano novo com aprovação nova.

## Consequências

- Instalação é reproduzível e auditável por hash — nunca "alguém rodou pip".
- A fronteira installer≠verifier é estrutural, não convencional.
- Especialista quebrado classifica como `INSTALLED_BROKEN` e volta ao
  pipeline — não é chutado para funcionar.
