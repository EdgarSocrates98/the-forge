# FASE 8.3 — Avaliação de UX

> Avaliação aplicada sobre o comportamento real observado nas fases 1–7
> e nas jornadas da FASE 8. Cada item marca o estado medido e a evidência.

## Navegação

| Superfície | Resultado |
|---|---|
| CLI | `theforge` bare imprime o sumário do produto ("one entry point, many specialists") com os verbos mais usados — descoberta em 1 comando. Idem `apiforge`, `sparkforge-aws`, `platformforge` (bare → help estruturado, fuzzy did-you-mean no api-forge) |
| TUI | Command-center com ações reais (não placeholders); menus validados contra o parser real por teste de contrato em cada repo |
| Recusa honesta | verbos sem TTY/caminho devolvem erro nomeado + hint, nunca traceback nem silêncio |

## Clareza

- Toda saída de observação distingue estados (`READY`/`SUPPORTED`/
  `NEEDS_LOGIN`/`NOT_DETECTED`/`DEGRADED`) — nada de "ok" ambíguo.
- Recusas nomeadas com `unlock`/hint (`AF-OPENAPI-UNSUPPORTED-VERSION`,
  `PF-*`, `host_absent`, `no_tty`, `login_required`).
- i18n en/pt compartilhado pelo kit canônico — mesmas chaves, mesma voz.

## Descobribilidade (descoberta)

- `capabilities list --json` publica o catálogo federado (declared_by,
  keywords, state, trust).
- `docs/learn/` em cada repo: trilha por nível + receitas
  problema→solução; `docs/hub/` do the-forge é o hub cross-forge
  (which-forge, hosts, install, mcp, recipes).
- `ask` resolve intenção natural → provider via sinais medidos —
  usuário não precisa conhecer o nome da forja.

## Onboarding

- Um comando: `./setup.sh`/`setup.ps1` → bootstrap governado
  (venv→runtime→launcher→register→verify), `--dry-run` audita antes.
- `install` com plano→aprovação; `doctor`/`status`/`repair`/`uninstall`
  completam o lifecycle; ledger sha256 garante posse honesta.
- Receita `primeiro-uso`/`instalar-*` em cada repo cobre o primeiro
  caminho valor-em-minutos.

## Recuperação (erros)

- Recusa nomeada + instrução de desbloqueio (padrão do design system).
- `install doctor`+`repair` recupera drift; `uninstall` remove só o
  gerenciado (ledger).
- Stale lock detectado e recuperado ("stale lock reclaimed").

## Consistência

- Mesmo contrato de host flow nos 7 repos (binário→versão→auth→
  integração→launch com as mesmas recusas).
- Mesmo installkit vendored byte-parity (`test_experience_parity`).
- Mesmo modelo de receita/índice/divergência-zero na documentação.
- i18n partilhado canonical + re-vended.

## Acessibilidade (terminal)

- NO_COLOR respeitado; fallback ASCII para terminais sem ANSI;
  non-TTY recusa explícita (nunca degrada em silêncio).
- Saídas `--json` completas para leitores de tela/scripts.
- i18n pt-BR nativo nos fluxos de instalação/hosts.

## Tempo de primeira tarefa

| Jornada | Comandos até valor | Decisões exigidas |
|---|---|---|
| Doctor API (J5) | 2 (`install` → `scan`) | 1 (aprovar plano) |
| The Forge (J6) | 2 (`init` → `ask`) | 0–1 (escolher host p/ launch) |
| Spark AWS (J1) | 3 (`setup.sh` → `install` → `analyze`) | 1 (aprovar plano) |

Meta do programa (mínimo esforço): atingida — nenhuma jornada pede mais
de 3 comandos nem decisões além do consentimento de instalação.

## Quantidade de decisões / comandos

- Instalação: 1 decisão (aprovar o plano) — o resto é default seguro.
- Operação diária: `observe`/`status` são zero-decisão; `launch` pede
  exatamente 1 escolha (qual host).
- Nenhum fluxo exige memorizar >3 verbos (`init|install` → `ask|scan`
  → `doctor`).

## Lacunas honestas

- TUI real depende de TTY humana — em CI só `--json` (por desenho).
- Copilot sem status de auth documentado (limite do vendor, declarado).
- Codex MCP em escopo de projeto é NOT_APPLICABLE (declarado no recibo).
- Browser real do Graph Studio não exercitado nesta sessão (servidor
  e payload verificados; clique é do operador).
