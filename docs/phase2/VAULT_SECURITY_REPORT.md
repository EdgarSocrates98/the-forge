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

## Testes executados

`uv run pytest -q -m "not benchmark" -rs` no Product Forge: **287 passed, 1 skipped, 3 deselected**. A skip é a
lane opcional de sistema instalado quando o opt-in não está habilitado; a lane
foi executada separadamente no Windows e passou (`1 passed`).

## Limitações

Permission denied foi validado com ACL real no Windows e disk full foi
validado em tmpfs real de 256 KiB: ENOSPC durante o lock retornou
`OBSIDIAN-LOCK-FAILED`/`sync_state=failed` sem nota, receipt ou temporário
parcial. Ainda falta executar esses cenários em host/vault produtivo. A
interrupção de processo tem teste determinístico local; isso não substitui a
matriz operacional de produção e multiusuário com revogação.
