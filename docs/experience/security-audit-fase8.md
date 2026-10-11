# FASE 8.8 — Auditoria de segurança

> Escopo: os 7 repos do ecossistema, superfícies expostas pela
> experiência (hosts, MCP, install, TUI, Graph Studio, delegação).
> Método: leitura de código + evidência de comportamento das fases —
> não é pentest; lacunas externas declaradas ao final.

## Credenciais e auth de hosts

| Controle | Estado |
|---|---|
| Saída de `auth status` nunca entra no recibo | **OK** — `hostflow`/`forge_hosts` carregam só o boolean `logged_in`; teste asserta ausência de caminho de credencial (`"secret" not in json.dumps`) |
| Host deslogado nunca é lançado | **OK** — recusa `login_required` + `login_hint` oficial |
| Nenhum comando lê/escreve arquivos de credencial | **OK** — a observação é via CLI oficial do vendor |
| Copilot auth | **Honesto** — sem comando de status documentado → `logged_in: null`, nunca inferido |

## Configuração de hosts e mirrors

- Mirrors de skills/agents são **saída de render** do canônico —
  `expected_agent_mirrors`/sync determinístico; edição manual vira
  drift detectável (`install doctor`).
- `AGENTS.md` recebe bloco delimitado `<forge>:managed:begin|end` —
  conteúdo do usuário fora dos marcadores nunca é tocado.
- Integração `unverified`/`DEGRADED` é reportada, não promovida.

## MCP

- Tools de host são **read-only** (`get_host_status`,
  `platformforge_hosts`, `sfa_ai`, `sparkforge_aws_ai`) — observam,
  nunca lançam; launch fica no CLI+TTY (fronteira humana).
- Handshake verificado de verdade (`mcp-verify`, invoke real) —
  "configurado" ≠ "verificado" respeitado.
- `devin mcp list` confirma registro nativo nos hosts reais.

## Trust e execução

- `task run` executa o argv declarado no manifesto do provider
  (`forge.agentic.json`) — fronteira: `task plan` antes (revisão),
  `stage`/`exit_code`/`stderr_tail` no recibo depois.
- `hosts launch` exige TTY + host explícito; `all` recusa nomear.
- Sem `shell=True` em `src/`/`scripts/` (auditoria textual) — todo
  subprocess é argv fixo com `check=False` e timeout.

## Installers e paths

- Pipeline governada discover→venv→install→launcher→register→verify;
  `--dry-run` audita sem escrever.
- **Ledger sha256** (`install-ledger.json`) é a fonte de posse:
  `uninstall` só remove `managed`; arquivos modificados pelo usuário
  são recusados/kept — prova de não-destruição.
- Lock de instalação com recuperação honesta ("stale lock reclaimed").
- Escrita limitada ao `root` do escopo + state dir próprio
  (`.forge/`, `.platformforge/`, `.forge-doctor*/`).

## Graph Studio server

- `http.server` stdlib, **bind 127.0.0.1** apenas; nunca expõe rede.
- Rotas fixas (`/`, `/api/health`, `/api/graphs`, `/api/graph/<id>`)
  com lookup por id — nenhum caminho de arquivo deriva da URL
  (sem path traversal).
- Browser só abre quando pedido (`--no-browser` respeitado); hint de
  ssh-forward impresso para uso remoto.

## Supply chain

- Kit de instalação vendored **byte-parity** com o canônico
  (`test_experience_parity` + `_VENDORED` hash no bootstrap).
- Dependências pinadas por repo (`uv.lock`/`pyproject` bounds);
  bootstrap é stdlib-only, rede só no passo explícito `pip install`.
- Sem telemetria, sem chamada de modelo — o core é offline
  (`no anthropic/openai/boto3` no core dos repos de análise).

## Permissões e rollback

- `uninstall` idempotente via ledger; `repair` restaura drift
  gerenciado; `status` é read-only.
- Recusas nomeadas (não exceções) para input inválido — `PF-*`,
  `AF-*`, `host_unknown`, `no_tty`.

## Lacunas declaradas

- Codex não lê `.mcp.json` de projeto → `NOT_APPLICABLE` registrado;
  alternativa documentada (`--scope user`/`codex mcp add`).
- `mcp-verify` exige o CLI da forja no PATH — falha honesta
  (`BLOCKED`/check FAIL), não finge handshake.
- Verificação de assinatura de artefatos de terceiros está fora de
  escopo (claimed ≠ verified respeitado).
- Delegação executa argv declarado — um manifesto malicioso num
  checkout local executaria seus próprios comandos; mitigação:
  manifesto é do repo da forja (confiança no clone) + `task plan`
  mostra o argv antes.
