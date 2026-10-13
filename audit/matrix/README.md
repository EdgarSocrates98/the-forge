# Validation matrix

Matrix central de evidências E2E. Cada linha deve conter comando executado,
SHA, ambiente, exit code, duração, artefato e classificação honesta.

`PASS` só é permitido após processo real bem-sucedido. `NOT_RUN` e `BLOCKED`
mantêm motivo preciso. A matriz não é dependência de runtime das Forjas.

Instalação tem matriz própria em `audit/reports/installer-matrix.json`, com
stdout/stderr por shell em `audit/artifacts/installers-*`. O relatório separa
dry-run de aplicação persistente; não confundir validação de wrapper com
alteração real de ambiente da conta.
