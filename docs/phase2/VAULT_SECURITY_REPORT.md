# Phase 2 — Vault Security Report

Estado: **PASS local; lacunas operacionais explicitadas**.

## Controles implementados

- path traversal, caminhos absolutos, extensões não Markdown e diretórios
  internos são recusados;
- symlink/reparse e hardlink são recusados em notas, diretórios e estado do
  adapter;
- vault fora de `FORGE_OBSIDIAN_ALLOWED_ROOT` é negado;
- classificação e tamanho são validados antes da operação;
- receipts, traces, projeções e relações não carregam o corpo da nota por padrão;
- conteúdo recebido do vault permanece não confiável e não ganha privilégios;
- escrita usa arquivo temporário, flush/fsync, replace atômico e hash posterior;
- lock por documento serializa mutações entre threads/processos suportados;
- API e Portal exigem confirmação explícita para import/export/rollback/skip.
- As projeções read-only dos quatro adapters também redigem `title`, `summary` e
  campos estruturados antes de gerar Markdown; cada adapter tem teste dedicado
  para impedir vazamento de token/password no corpo da nota.

## Testes executados

`uv run pytest -q -m "not benchmark" -rs` no Product Forge: **287 passed, 1 skipped, 3 deselected**. A skip é a
lane opcional de sistema instalado quando o opt-in não está habilitado; a lane
foi executada separadamente no Windows e passou (`1 passed`).

O subconjunto operacional de sync foi revalidado em 2026-11-10 com
`uv run pytest -q tests/test_obsidian.py -k "process_exit or rollback or atomic or permission or lock or concurrent or manual"`:
**11 passed, 39 deselected**, incluindo conflito de edição manual e rollback
sem sobrescrita silenciosa.

## Limitações

Permission denied foi validado com ACL real no Windows e disk full foi
validado em tmpfs real de 256 KiB: ENOSPC durante o lock retornou
`OBSIDIAN-LOCK-FAILED`/`sync_state=failed` sem nota, receipt ou temporário
parcial. Ainda falta executar esses cenários em host/vault produtivo. A
interrupção de processo tem teste determinístico local; isso não substitui a
matriz operacional de produção e multiusuário com revogação.
