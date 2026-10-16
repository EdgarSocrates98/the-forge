# Gap Register — Cycle 10.1

Registro vivo dos gaps auditados neste ciclo. Cada entrada: severidade, causa-raiz, correção, evidência.

| ID | Prioridade | Área | Problema | Causa-raiz | Correção | Evidência | Status |
|---|---|---|---|---|---|---|---|
| GAP-01 | P0 | Certificação | Homologação anterior registra `CERTIFICATION_BLOCKED`; evidências dos Cycles 8–10 não promovidas | tooling de audit era Windows-only (linux-bash hardcoded BLOCKED; MCP sem fallback .venv); `.pytest-tmp` poluía lab do doctor-api | H0–H7 reexecutados em Linux nos SHAs atuais; tooling corrigido; doc canônico atualizado | `linux-acceptance.md`, `installer-matrix.json`, `mcp-handshake.json` 6/6, `evidence-index.json` 19/19, lab 7/7 203 cenários, CI 9/9 | in_progress (H3/H4/H6 aguardam cyc101-04/05/07) |
| GAP-02 | P0 | Portal E2E | Integração visual real Portal × múltiplas Forjas sem evidência completa reproduzível | a executar | — | — | open |
| GAP-03 | P0 | CLI lifecycle | Update/downgrade/rollback/repair/uninstall não homologados integralmente | a executar | — | — | open |
| GAP-04 | P0 | Hosts/MCP | Handshakes MCP locais não provam que hosts usam as configs instaladas | a executar | — | — | open |
| GAP-05 | P0 | Release/RC | Nenhum repo possui release candidate versionado e verificável | a preparar | — | — | open |
| GAP-06 | P1 | Forge Lab | Conteúdo das evidências (203 cenários) não auditado — só a coleta foi | a validar | — | — | open |
| GAP-07 | P0/P1 | Segurança | Auditoria de dependências/supply-chain precisa ser reexecutada nos commits atuais | a auditar | — | — | open |
| E2E-GLOBAL | P0 | Integração | Fluxo global obrigatório §10 ainda não executado com relatório verificável | a executar | — | — | open |

Status possíveis: `open`, `in_progress`, `closed`, `blocked-external` (exige bloqueio externo documentado).
