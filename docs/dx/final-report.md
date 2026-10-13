# Forge DX & Documentation — relatório consolidado (prompt_evo_docs)

Branch: `feat/dx-docs` em todos os 7 repos.
Status vocabulary: PASS / FAIL / BLOCKED / UNVERIFIED / NOT_APPLICABLE.

## Resumo executivo

Programa DX entregue em 5 ondas: (0) inventário real de comandos via
parser, (1) Forge Documentation & CLI Experience Standard v1, (2) docs
geradas por repo, (3) descobribilidade de CLI, (4) multilíngue +
handbook + validação como código + matriz de usabilidade.

## Por projeto

```text
PROJECT:                THE-FORGE / API-FORGE / SPARKFORGE-AWS /
                        SPARKFORGE-AZURE / PLATFORMFORGE /
                        FORGE-DOCTOR-DATA / FORGE-DOCTOR-API
BRANCH:                 feat/dx-docs (7 repos)
COMMIT:                 ver `git log --oneline feat/dx-docs`
COMMANDS DISCOVERED:    63 / 443 / 242 / 93 / 57 / 289 / 35  (=1222)
COMMANDS DOCUMENTED:    todos via docs/reference/commands.md (gerado)
COMMANDS MISSING DOCS:  0 doc-missing em 5/7; AWS 3 e doctor-api 1
                        residuais em docs congelados/legendas
COMMANDS IMPROVED:      bare summary (4 CLIs), help <verbo> (4),
                        did-you-mean (todos), resumo bare apiforge
README:                 índice DX adicionado (6); the-forge via seção
                        Documentação
QUICKSTART:             pt + en por repo
INSTALLATION GUIDE:     docs/installation/ (12 guias por repo)
PORTABILITY GUIDE:      portable-installation.md + workspace-installation.md
HOST INTEGRATIONS:      claude-code, devin-cli, codex-cli, copilot-cli
MCP GUIDE:              mcp.md por repo; the-forge NOT_APPLICABLE
SKILLS CATALOG:         docs/reference/skills.md (33/15/60/22/12/0/0)
AGENTS CATALOG:         docs/reference/agents.md (8/32/19/40/41/0/0 —
                        doctors honestamente vazio)
TUTORIALS:              docs/tutorials/first-run.md por repo, classificado
TROUBLESHOOTING:        pt + en por repo
PT-BR:                  PASS (idioma principal dos guias)
ENGLISH:                PASS (quickstart + troubleshooting)
BROKEN LINKS:           0 (check_docs, ~2869 arquivos md)
INVALID EXAMPLES:       0 comandos documentados-inexistentes nos guias
                        mantidos; residuais só em archive/specs congelados
AUTOMATED TESTS:        check_docs gate PASS nos 7; test_cli.py +3 casos
                        no the-forge (bare/help/did-you-mean)
REAL EXECUTION TESTS:   bare/help/suggest rodados em 5 CLIs; MCP real
                        handshake em doctor-data (13 tools + invoke)
USABILITY FINDINGS:     docs/dx/usability-matrix.md — 9 EXECUTED, 2 PENDING
REMAINING GAPS:         execução real dentro dos hosts (UNVERIFIED);
                        multi-OS (UNVERIFIED); MCP handshake real em
                        api/azure/platform/doctor-api (UNVERIFIED — deps)
FINAL STATUS:           PASS (com gaps honestos registrados)
```

## Matriz do ecossistema

| Área | the-forge | api | aws | azure | platform | d-data | d-api |
|---|---|---|---|---|---|---|---|
| Inventário real | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| Referência gerada | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| Bare/help/suggest | PASS | PASS | PASS | PASS | PASS | PASS* | N/A** |
| Install docs | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| Tutorials | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| Troubleshooting | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| pt+en | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| MCP real verify | N/A | UNVERIFIED | FAIL(honesto) | UNVERIFIED | UNVERIFIED | PASS | UNVERIFIED |
| check_docs gate | PASS | PASS | PASS | PASS | PASS | PASS | PASS |

*doctor-data já tinha `no_args_is_help` + epilog + painéis.
**doctor-api: surface travada por release-candidate — ciclo de vida via
`scripts/forge_install.py` (documentado, não modificado).

## Ferramentas entregues (scripts/docs/, vendored nos 7)

- `doc_inventory.py` — inventário do parser real (argparse/click/typer
  duck-typed), divergence fenced-block com posição de invocação.
- `doc_reference.py` — commands.md gerado, keep-blocks preservam notas.
- `doc_catalogs.py` — skills/agents catalogs; .md dirs + AgentSpec TOML.
- `check_docs.py` — gate: links, âncoras (unicode-aware), comandos em
  fences vs inventário, status claims. Excludes configuráveis.

## Divergência corrigida nesta wave

- the-forge: 8 comandos documentados-inexistentes → 0.
- api-forge: `install mcp-verify`/`install repair|update|uninstall`
  corrigidos nos guias; 16 → 0.
- azure/platform/doctor-data/doctor-api: mesma classe de erro corrigida.
- aws/azure/platform: links quebrados em docs sdd/superpowers (17) fix.
- Residual intencional: aws 3 (specs/arquivos congelados citando
  capacidades futuras — marcado, não "corrigido" pois é histórico),
  doctor-api 1 (linha-legenda `forge-doctor-api deterministic` numa
  tabela fenced — não é invocação).
