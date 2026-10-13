# Acceptance matrix — §15 E2E + §12 cenários

Status per scenario with fresh evidence. `covered` = automated test
exists and passes; `ran` = executed against a real artifact during
implementation; `pending` = gate honestly open, never claimed.

## §15 — Testes end-to-end

| § | Cenário | Status | Evidência |
|---|---|---|---|
| 15.1 | clone → setup → CLI → install → doctor → MCP → invoke | ran + covered | bootstrap E2E executado na fase 2 (wheel instalado, `theforge 0.5.0` no PATH, launcher funcional); `test_install_e2e.py`; `test_mcp_verify_real_handshake_and_invoke` (doctor-data real: 13 tools + tools/call PASS) |
| 15.2 | segunda instalação idempotente, sem duplicar skills/agentes/bloco MCP | covered | `test_e2e_matrix.py::test_clean_install_then_second_apply_is_idempotent`, `test_marker_block_not_duplicated_on_reapply`, `test_mcp_key_not_duplicated_on_reapply` |
| 15.3 | instalar versão anterior, atualizar, manifesto migra e configs do usuário preservadas | partial | `update` exige `--to` pinado e recusa `latest` (`test_update_rejects_latest`); preservação de configs coberta por `test_apply_preserves_user_agents`. Migração de manifesto de uma *versão anterior real*: **pending** — requer artefato publicado anterior, não existe ainda |
| 15.4 | remover arquivo gerenciado → `repair` restaura sem tocar terceiros | covered | `test_repair_restores_deleted_managed_file_only` + suíte repair (`test_installkit.py`) |
| 15.5 | `uninstall` remove somente o gerenciado | covered | `test_uninstall_removes_only_managed_leaves_user_content`, `test_uninstall_keeps_modified_managed_file` |
| 15.6 | interrupção em venv/pacote/assets/registro/verificação → rollback ou recuperável | covered | write-stage: `test_failed_write_reverts_to_prior_state`, `test_rollback_on_write_failure`, `test_rollback_removes_created_and_restores_updated`; lock de processo interrompido: `test_stale_lock_reclaimed`, `test_stale_lock_from_interrupted_run_is_recovered`. Bootstrap falha honestamente em cada estágio (venv/pip/launcher/report) |
| 15.7 | Claude, Devin, Codex, Copilot — estrutural vs execução real | structural covered / real pending | `test_host_dirs_are_distinct_per_host` (4 hosts renderizados); execução real em hosts instalados: **pending** — gate registrado, nunca declarado |
| 15.8 | CI Linux/Windows/macOS | pending | sem pipeline CI no repo; gate registrado como pendente — compatibilidade **não** declarada por revisão estática |
| 15.9 | offline / artefato ausente | covered | `test_mcp_verify_blocked_when_exe_missing_is_honest`, `test_mcp_verify_unresolvable_exe_blocked`, `test_auto_empty_registry` (BLOCKED real, nunca mascarado) |

## §12 — Cenários de aceitação externos

| Cenário | Status | Evidência |
|---|---|---|
| A — `sparkforge-aws install --host devin` + doctor em projeto externo | ran | lifecycle completo install→status→doctor→uninstall em dir temporário externo (fase 3); doctor reporta SDK MCP ausente honestamente |
| B — `apiforge install --host claude` + doctor | ran | lifecycle recommended+full em temp dir (fase 4); doctor+repair verificados |
| C — `theforge install auto --dry-run` reconhece especialistas | covered + ran | `test_install_orchestration.py` (registry → delegation → BLOCKED honesto); smoke real com `install_command` em workspace fake |
| D — `install auto --scope workspace` multi-repo | covered + ran | `test_workspace_scope`, discovery real em workspace de 3 repos fake com delegação |
| E — novo terminal, launcher persiste sem ativar venv | ran | launcher `theforge` executado de shell nova após bootstrap (fase 2) |
| F — MCP handshake + invocação segura pela config instalada | ran | handshake real doctor-data: initialize→13 tools→`tools/call` PASS→exit limpo (fase 8) |
| G — smoke em Claude Code + Devin CLI reais | pending | CLIs presentes no host, mas gate de execução real em host registrado como pendente — não aprovado por mock |

## Regra

`pending` nunca conta como suporte validado. Quando um gate pendente
for executado, esta tabela é atualizada com a evidência do run.
