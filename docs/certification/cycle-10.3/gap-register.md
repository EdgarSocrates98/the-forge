# Cycle 10.3 — Gap Register

Gaps reais encontrados durante a auditoria. Cada item tem severidade, evidência
e destino proposto. Nada aqui é hipótese — tudo tem reprodução ou fonte citada.

## G-DOCS-1 — PyPI README não ensina `pip install` (alta) — ✅ CORRIGIDO

`theforge-core` no PyPI mostrava só instalação por checkout (clone + `-e
.[dev]` + `./setup.sh`). Corrigido 2026-10-17: `pip install <dist>` agora
lidera a seção Install dos 7 READMEs (the-forge, api-forge, platform-forge,
spark-forge-azure, forge-doctor-api ganharam a seção; spark-forge-aws e
forge-doctor-data já tinham registry install).

## G-DOCS-2 — Logo quebrado no PyPI (baixa) — ✅ CORRIGIDO

`<img src="docs/assets/logo_forge.png">` e as outras 6 imagens relativas →
`raw.githubusercontent.com/.../<tag>/` — todas as 7 logos agora renderizam.

## G-DOCS-4 — ~350 links relativos quebrados no PyPI (alta) — ✅ CORRIGIDO

Encontrado pelo revisor do ciclo (a auditoria original certificou "1 link").
343 links markdown + 7 imagens nos 7 READMEs registry-bound eram 404
garantidos no PyPI (ele não reescreve relativos). Reescritos para URLs
absolutas pinadas na tag da release (`blob/` arquivo, `tree/` dir,
`raw.githubusercontent/` imagem), 0 alvos faltantes. PRs: #74, #81, #47+#51, #168,
#62, #48, #60.

## G-DOCS-3 — CLI npm não referenciado nos READMEs (média) — parcial

`theforge-cli` (npm) agora é referenciado no README do the-forge. Os READMEs
das forjas individuais não o mencionam — decisão razoável (cada forja é
independente; o instalador é opt-in). Mantido como observação, não bloqueio.

## G-CLI-1 — forge-cli é clone-only (feature)

`install` faz `git clone` + build local; não há rota `pip install <dist>` nem
fallback. Funciona (23s medido) mas exige git e compilação local. **Destino**:
spec de feature (cyc11), não patch — muda o mecanismo central.

## G-DX-1 — `apiforge-mcp` sem extra → traceback cru (baixa) — ✅ CORRIGIDO

Causa raiz encontrada no review: `build_server` levanta `RuntimeError`
(AF-MCP-OPTIONAL-UNAVAILABLE) mas `main.py` só capturava `ImportError` → a
mensagem guiada existia e era **inalcançável**. Fix (refinado no 2º review):
`except ImportError` + `except RuntimeError` filtrado por
`AF-MCP-OPTIONAL-UNAVAILABLE` (RuntimeErrors reais propagam), unlock
`apiforge-af[mcp]`, exit 2 — com teste de contrato
(`test_main_missing_extra.py`, 3 casos).

## G-RENAME-1 — dist name morto em runtime do adapter (alta) — ✅ CORRIGIDO

`version("apiforge")` (dist morta → provenance "unknown" silenciosa) e 5
mensagens `install apiforge` no adapter theforge_apiforge; `README.pt-BR.md`
com `pip install 'apiforge[all]'`. Corrigido: lookup `apiforge-af`→`apiforge`
(fallback dev), mensagens e doc apontam `apiforge-af`.

**Errata (review 4):** a marcação anterior estava incompleta — o rename não
havia alcançado o control plane: `forge-knowledge/api-forge.json`
(`package`/`install.command` = `apiforge>=0.1,<0.2`, 404 no PyPI — o comando
era executado verbatim por `install auto`) e `agentic/skills/forge-api.md`
(mesmo spec morto + `tested_version 0.3.0`, propagado aos mirrors
`.claude`/`.agents`/`.devin` e ao wheel `host_assets`). Corrigido agora:
`apiforge-af>=0.1,<0.2` em ambos, mirrors re-renderizados, `tested_version`
alinhado ao publicado (0.1.0).

## G-TEST-1 — doc gates irmãos pulavam URLs absolutas (média) — ✅ CORRIGIDO

`doc_manifest._check_links` ignorava `https://` → os ~330 links convertidos
perderam cobertura missing-file/anchor. Resolver portado aos 6 repos (slug
derivado de `pyproject.urls`, escapes `..` rejeitados); the-forge ganhou
`resolve_repo_url` com a mesma semântica. READMEs convertidos validam 0
findings.

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

## G-ONB-1 — Golden paths falhavam no primeiro comando (alta) — ✅ CORRIGIDO

`docs/onboarding/golden-paths/{api,platform,spark-aws}.md` e 4 guias
getting-started instruíam `theforge install <pkg>` — `install` só aceita
subcomandos (`plan|apply|status|doctor|repair|uninstall|update|auto|mcp-verify`)
e `apiforge` nem era o provider id. Corrigido: `theforge install auto --forge <id>`
(api-forge, platform-forge, spark-forge-aws, spark-forge-azure). Gate
`check_onboarding.py` endurecido: valida `theforge <verb> <sub>` contra o
grupo `{...}` de cada `--help` (falso positivo anterior impossível —
comando inválido reproduzido em teste negativo).

## G-TEST-2 — `_check_links` ignorava `#fragment` em URLs mapeadas (média) — ✅ CORRIGIDO

`_repo_url_path` stripa `#` internamente; `mapped.partition("#")` retornava
frag vazio → anchors nunca verificados em links tag-pinned (7 READMEs com
`#frag` vivos desprotegidos). Corrigido nos 7 `doc_manifest.py`: frag vem de
`raw.partition("#")`; `%23` decodificado dentro do path é caractere de nome,
não separador; `#L10`/`#L10-L20` (line anchors GitHub) isentos do check.
+3 testes novos por repo (missing-anchor, valid-anchor, line-ref).
