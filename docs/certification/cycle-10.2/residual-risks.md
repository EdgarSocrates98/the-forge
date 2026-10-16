# Residual Risks — Cycle 10.2

| Risco | Estado |
|---|---|
| Push das branches (9 repos) | BLOQUEADO: token OAuth sem scope `workflow`; requer `gh auth refresh -s workflow` ou push manual |
| Copilot host | NOT_TESTED (ausente) |
| Firefox/WebKit | não executado |
| Windows nativo | só CI matrix |
| spark-forge-azure | adapter instalável mas não acionado no E2E |
| platform-forge | READY; não foi selecionado como primary nos intents testados (candidato no decision) |
| §6.5 multi-agent lab | PARTIAL (10.1) |
| SBOM formal (CycloneDX/Syft) | follow-up; atuais = pip freeze / lockfiles |
