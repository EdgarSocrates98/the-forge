# Phase 2 — Cross-Forge Obsidian E2E Evidence

Data da execução: 2026-11-09

## Escopo

Este ensaio verifica o contrato e as fronteiras de integração em um vault
temporário, com fixtures locais produzidas pelos adapters de AWS, Azure, API e
Platform. A mutação controlada usa a distribuição neutra `forge_obsidian`, não o
runtime de aplicação do Product Forge. Ele não acessa cloud, não usa um vault de usuário e não é evidência
de homologação operacional em AWS/Azure.

## Comando reproduzível

```powershell
cd E:\projetos\FORJAS\the-forge
uv run python scripts/phase2_federated_obsidian_e2e.py `
  --repos-root E:\projetos\FORJAS
```

O runner cria uma pasta temporária, cria os diretórios dos documentos, executa
export/import pelo `forge_obsidian` e remove o vault ao terminar. Nenhum checkout
é modificado.

## Resultado observado

```json
{
  "schema": "theforge/Phase2FederatedObsidianE2E/v1",
  "fixture_only": true,
  "notes_exported": 4,
  "notes_roundtripped": 4,
  "atlas_relations": 1,
  "lens_spans": 1,
  "bridge_authorized": true,
  "manual_conflict_detected": true,
  "cloud_access": false,
  "body_persisted_in_federation_outputs": false
}
```

O resultado comprova, em conjunto:

- os quatro adapters produzem `theforge/ObsidianNoteRef/v1` com proveniência;
- o runner chama diretamente `forge_obsidian`, mantendo o Product Forge fora
  do núcleo técnico de import/export;
- o Markdown exportado e importado preserva o conteúdo e o hash;
- o Code Atlas recebe somente relações documentais, sem corpo da nota;
- o Forge Lens recebe um trace sanitizado, sem corpo da nota;
- o Agent Bridge autoriza o source somente após allowlist explícita;
- uma edição manual entre plano e export é reportada como conflito e não é
  sobrescrita.

## Limites da evidência

Ainda não está comprovado por este runner: cloud real, Portal disparando a
execução do runner de fixtures, handoff produtivo do recibo de investigação ao
Product Forge, gravação automática no Obsidian, provisionamento multiusuário de vault, rename/delete em
escala, falha de disco/permissão ou ensaio instalável pelo Portal. O Product
Forge possui gates locais separados para rename/delete, lock concorrente entre
processos, kill recovery e benchmark de 10.000 notas; eles não devem ser
inferidos como operação federada ou de produção a partir deste resultado.

O Portal possui uma lane runtime independente e validada para
`/investigations/plan` → `/investigations/run` → `GET /investigations`, com plano
assinado, confirmação explícita e persistência redigida de
`OrchestrationReport`. O handoff Portal → Product Forge possui testes de API e
frontend separados, com deduplicação e projeção sem corpo de resposta; essa
lane não é incorporada ao runner fixture-only para manter a evidência de
formato, a evidência de orquestração e a evidência de indexação separadas.
