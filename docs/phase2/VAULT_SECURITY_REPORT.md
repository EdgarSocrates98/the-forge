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

`uv run pytest -q -rs` no Product Forge: **256 passed, 1 skipped**. A única
skip é a lane opcional de sistema instalado, não contada como aprovação.

## Limitações

Ainda falta executar em ambiente controlado uma permissão negada real, disco
cheio real, interrupção de processo no meio da operação e matriz multiusuário
com revogação. Até lá, essas condições permanecem gates separados.
