# Cycle 10.3 — Gap Register

Gaps reais encontrados durante a auditoria. Cada item tem severidade, evidência
e destino proposto. Nada aqui é hipótese — tudo tem reprodução ou fonte citada.

## G-DOCS-1 — PyPI README não ensina `pip install` (alta)

`theforge-core` no PyPI mostra "Instalação (desenvolvimento)" (clone + `-e
.[dev]`) e "Instalação portátil" (`./setup.sh`) — ambos exigem checkout git.
Nenhuma menção a `pip install theforge-core`. Usuário que chega pela página do
pacote não descobre o caminho trivial. **Destino**: patch docs (adicionar à
PR #74 ou PR nova). Mesmo problema em outros pacotes que só documentam clone.

## G-DOCS-2 — Logo quebrado no PyPI (baixa)

`<img src="docs/assets/logo_forge.png">` relativo → não renderiza no
long_description. **Destino**: patch docs (URL absoluto pinado).

## G-DOCS-3 — CLI npm não referenciado nos READMEs (média)

`theforge-cli` existe no npm mas nenhum README de forja o menciona — usuário
PyPI não descobre o instalador. **Destino**: patch docs.

## G-CLI-1 — forge-cli é clone-only (feature)

`install` faz `git clone` + build local; não há rota `pip install <dist>` nem
fallback. Funciona (23s medido) mas exige git e compilação local. **Destino**:
spec de feature (cyc11), não patch — muda o mecanismo central.

## G-DX-1 — `apiforge-mcp` sem extra → traceback cru (baixa)

`ModuleNotFoundError: mcp.server.mcpserver` em vez de mensagem guiada.
**Destino**: patch — catch + "instale apiforge-af[mcp]".

## G-MATRIX-1 — requires-python floor não testado em CI (média)

| Pacote | Declara | CI testa | Floor real? |
|---|---|---|---|
| platformforge | >=3.10 | só 3.12 | 3.10/3.11 nunca exercitados |
| sparkforge-aws | >=3.10 | 3.11, 3.12 | 3.10 nunca exercitado |
| sparkforge-azure | >=3.10 | só 3.12 | 3.10/3.11 nunca exercitados |
| theforge-core | >=3.11 | 3.11, 3.12 | 3.13 permitido, não testado |

Usuário em 3.10 instala (metadata permite) e roda código nunca testado.
**Destino**: decisão — ampliar matrix CI (sem release) **ou** subir
`requires-python` ao floor testado (patch). Aguarda decisão do dono.

## G-REG-1 — theforge-core sdist: hash PyPI ≠ asset GitHub (auditável)

Wheel bate; sdist não bate com nenhum asset do Release v0.5.0 — o upload PyPI
foi de um rebuild posterior (rename `the-forge`→`theforge-core`). Sem
inconsistência de conteúdo detectada, mas a proveniência do sdist diverge do
asset assinado. **Destino**: documentar; próxima release via OIDC emite
attestation que resolve proveniência.

## G-REG-2 — GitHub Release api-forge v0.1.0: assets `apiforge-*` stale (auditável)

Tag v0.1.0 é pré-rename (`name = "apiforge"`); PyPI `apiforge-af` saiu de
commit posterior. Assets do release GH carregam nomes antigos. **Destino**:
patch release v0.1.1 resolve de uma vez (tag nova já contém rename+metadata).

## G-LAB-1 — `lab collect` usa interpretador do registry (design)

`{python}` = `FORGE_*_PYTHON` (system python na instalação), não o venv
gerenciado → cenários extras-gated sempre `skipped` no contexto federado.
Correto agora que skip ≠ fail (fda#61), mas significa que extras nunca
exercitam no lab federado. **Destino**: decisão de design — apontar
`{python}` pro venv ou documentar a limitação.

## G-E2E-1 — Agents funcionais por host: declarado, não testado

Presença de arquivos de integração nos hosts: verificada. Eficácia de cada
agent dentro de cada host (sessão real): não exercitada. **Destino**: ciclo
futuro de E2E agentic — não é defeito, é cobertura honesta.

## G-HOME-1 — `homepage` GitHub vazio nos 9 (baixa)

Campo settings sem URL. **Destino**: edição de settings (sem release) —
apontar PyPI/npm.

## G-WIKI-1 — `has_wiki` ligado em 3 repos (baixa)

spark-forge-aws, spark-forge-azure, forge-doctor-data. Wiki vazia ou ligada
por acidente. **Destino**: verificar conteúdo ou desligar (settings).

## G-SEC-1 — Token PyPI exposto na sessão Release 1 (higiene)

Token `pypi-AgEI...` circulou em texto. OIDC já cobre publicações.
**Destino**: rotação/revogação pelo dono — já recomendado, ação humana.
