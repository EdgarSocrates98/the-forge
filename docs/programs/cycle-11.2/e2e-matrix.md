# Cycle 11.2.1 §16 — E2E matrix real (A–N)

Execução real de ponta a ponta do ecossistema Forge em **2026-10-17/18**,
ambiente hermético: `FORGE_CLI_HOME=/tmp/forge-e2e-matrix/home`,
`HOME` redirecionado para o mesmo dir, `npm --prefix
/tmp/forge-e2e-matrix/npm`, venvs em `/tmp/forge-e2e-matrix/venvs`.
Nada tocou `~/.forge` ou o prefix npm reais do usuário. Host: Linux
x86_64, node v22.23.2, npm 10.9.8, python3 do sistema 3.12.3 mais
interpretadores uv (3.10.21 / 3.11.16 / 3.13.15 / 3.14.7 em
`~/.local/bin/python3.*`). Rede real usada só para registradores
públicos (npmjs, PyPI).

Artefato publicado sob teste: **`theforge-cli@0.2.0`** (npm,
publicado 2026-10-17T14:44Z por GitHub Actions OIDC). Achado
transversal: o tarball publicado **anterior ao merge do PR #30**
(commit `3789318`) — faltam `--version` self-print, `registry lock` /
`--lock` (offline-lock.json), allowlist `mcp_safe_tools` (tools/call) e
o chooser registry-first da TUI. Todas as divergências estão
detalhadas nas pernas abaixo.

## Resultado por perna

| Perna | Escopo | Veredito |
|---|---|---|
| A | npm install limpo, --help/--version/first-run/preflight | **PARTIAL** |
| B | registry-first: 2 Forjas do PyPI sem clone | **VERIFIED** |
| C | install→update→pin→unpin→rollback→repair→uninstall | **VERIFIED** |
| D | offline via cache + hashes | **VERIFIED** (ressalva: `registry lock` ausente no 0.2.0) |
| E | MCP initialize→tools/list→tools/call | **VERIFIED** (ressalvas) |
| F | registro MCP em host real + preservação/rollback | **VERIFIED** |
| G | portal em Chromium real + cookie de sessão + ops UI | **VERIFIED** |
| H | Forge Lab com/sem extras | **VERIFIED** |
| I | pisos Python das 7 dists PyPI | **VERIFIED** |
| J | fault injection (state corrompido, uninstall parcial) | **VERIFIED** |
| K | independência sem forge-cli no PATH | **VERIFIED** |
| L | integridade da release (npm sig/attestations, hashes PyPI) | **VERIFIED** (lacuna: PyPI sem PEP 740/sig) |
| M | theforge descobre especialistas, executa, recibo | **PARTIAL** |
| N | README público literal em subshell limpo | **VERIFIED** (lacunas de doc registradas) |

---

## A — Clean npm install

```text
$ npm install -g theforge-cli --prefix /tmp/forge-e2e-matrix/npm
added 33 packages in 2s
$ ls /tmp/forge-e2e-matrix/npm/bin/
forge-cli -> ../lib/node_modules/theforge-cli/dist/index.js
```

- **Bin publicado: `forge-cli`** (package.json `"bin": {"forge-cli": ...}`).
  Não existe `theforge-cli` executável — o nome npm é só o da dist.
- `forge-cli --help` → exit 0, ajuda completa (todos os subcomandos).
- `forge-cli --version` → **exit 1**: `Option '--version <value>'
  argument missing` — no 0.2.0 publicado `--version` é só a flag de pin;
  o self-print (`versionFlag`) existe em `origin/main` (dist local tem
  `versionFlag`, publicado não). `forge-cli version` → `Comando
  desconhecido: version`.
- First run sem TTY: banner → preflight (`Git disponível`, `Node.js
  >= 20 (v22.23.2)`, `Python 3 disponível (3.14.7)` — o CLI probe
  PYTHON_MINORS=[14,13,12,11,10] e achou o uv-managed 3.14.7) → prompt
  de diretório → EOF cancela limpo.
- First run com TTY real (pty): menu → `Instalar Forjas` → preflight →
  dir → seleção (8/8 por padrão) → plano por repo com origem/comandos →
  confirmação → `No` → `Operação cancelada pelo usuário.` exit limpo.
- `forge-cli list` / `forge-cli registry` / `forge-cli status --json` →
  funcionam, exit 0.
- **DEFEITO real**: `forge-cli doctor` (e `forge-cli hosts list`)
  **travam >4 min** quando um shim de host no PATH não retorna:
  `ps` mostrou `/bin/sh /home/edgar/.local/bin/cursor --version` girando
  a 72% CPU. Causa: `commandOutput` em `src/utils/system.ts:83` chama
  `execa(..., {reject:false})` **sem timeout**; `hosts/types.ts` usa
  esse probe para `versionArgv` de cada host. Sem timeout por probe nem
  kill — morto manualmente após ~4min sem saída além do banner.

Veredito A: **PARTIAL** — install/help/preflight/TUI verificados;
`--version` ausente no artefato publicado; doctor/hosts-list têm hang
real por probe sem timeout.

## B — Registry-first (PyPI, sem clone)

```text
$ forge-cli install the-forge --method registry --yes
●  Python detectado: 3.14.7, 3.13.15, 3.12.3, 3.11.16, 3.10.21
◇  the-forge: instalado theforge-core==0.5.0
◇  the-forge → .../.forge-cli/forges/the-forge/venv/bin/theforge
└  ✅ instalação registry-first concluída

$ forge-cli install spark-forge-aws --method registry --yes
◇  spark-forge-aws: instalado sparkforge-aws==0.5.0
└  ✅ instalação registry-first concluída
```

Receipts (`~/.forge-cli/forges/state.json` + `install.json`) provam:
`requiresPython>=3.11`→venv python `3.14.7` (mais novo que satisfaz),
`files[]` com sha256 do wheel **e** do sdist, `verifiedHash`,
`provenance.resolvedVia: pypi`, `verify.ok:true` (`bin --help` rodado
pós-install). Nenhum `git clone` ocorreu — `forge-workspace/` não tem
repos. Bins respondem direto:

```text
$ .../the-forge/venv/bin/theforge --version
theforge 0.5.0
$ .../spark-forge-aws/venv/bin/sparkforge-aws --version
sparkforge-aws 0.5.0
```

Veredito B: **VERIFIED**.

## C — Lifecycle completo (forge-doctor-data)

Estado snapshotado em `~/.forge-cli/forges/state.json` entre passos.

| Passo | Comando | Resultado |
|---|---|---|
| install | `install forge-doctor-data --method registry --yes` | 1.0.0 instalado, venv 3.14.7 |
| update | `update forge-doctor-data --method registry --yes` | `já na mais recente` / `nada a atualizar` (PyPI só tem 1.0.0) |
| pin | `pin forge-doctor-data --version 1.0.0 --method registry` | `Fixada em 1.0.0`; receipt ganhou `"pinned": "1.0.0"` |
| update c/ pin | `update forge-doctor-data --method registry --yes` | `forge-doctor-data: fixada em 1.0.0` → pin respeitado |
| unpin | `unpin forge-doctor-data --method registry` | `Fixação removida` |
| rollback | `rollback forge-doctor-data --method registry --yes` | **recusa honesta**: `sem revisão anterior registrada` (release única, sem histórico) |
| repair | apaguei `.../contracts/fixtures/capability.json` da venv → `reinstall forge-doctor-data --method registry --yes` | arquivo restaurado, exit 0 |
| uninstall | `uninstall forge-doctor-data --method registry --yes` | `forge-doctor-data: removido` — venv + wheel cache + receipt fora; `state.json` consistente; metadata PyPI (`cache/pypi/*.json`) retida |

Quirks observados (não bloqueantes): `pin` **sem** `--method registry`
vai para o state git-method (`<dir>/.forge-cli/state.json` —
`pins.forge-doctor-data`), não para o receipt registry; `update --check
--method registry` **sem nomes nem `--all`** responde `nenhuma Forja
instalada via registry` mesmo com 3 instaladas (com nomes ou `--all`
lista `0.5.0 → 0.5.0 (já na mais recente)` corretamente).

Veredito C: **VERIFIED**.

## D — Offline

Mecanismo do artefato publicado: `--offline` resolve só pelo cache
(`~/.forge-cli/cache/pypi/*.json` + `cache/wheels/<dist>/`) e o pip roda
`--no-index --find-links <wheels>` (src/registry/install.ts). O fecho
transitivo com hashes (`registry lock` → `*.offline-lock.json` + flag
`--lock`) **existe só no repo (commit 3789318)** — publicado 0.2.0 não
tem `generateOfflineLock`/`--lock` (verificado no dist instalado).

```text
# D1 — sem cache nenhum → recusa honesta
$ forge-cli install forge-doctor-api --method registry --offline --yes
■  forge-doctor-api: sem cache local e --offline ativo — rode online uma vez

# D2 — metadata em cache mas artefato evictado pelo uninstall → recusa 2
$ forge-cli install forge-doctor-data --method registry --offline --yes
■  forge-doctor-data: artefato ausente no cache local — instalação
   offline impossível: forge-doctor-data==1.0.0: sem wheel/sdist em
   .../cache/wheels/forge-doctor-data — instale online uma vez

# D3 — cache semeado via `pip download` (mesmo mecanismo do registry lock
#      do HEAD: fecha o fecho transitivo com wheels em cache/wheels/<dist>/)
$ python3.14 -m pip download forge-doctor-data==1.0.0 \
    --dest ~/.forge-cli/cache/wheels/forge-doctor-data   # 9 wheels (fecho)

# D4 — install --offline com TODOS os proxies mortos (qualquer acesso de
#      rede do pip falharia; `unshare -n` indisponível no host)
$ env -i PATH=... FORGE_CLI_HOME=... HOME=... \
    HTTP_PROXY=http://127.0.0.1:1/ HTTPS_PROXY=http://127.0.0.1:1/ \
    ALL_PROXY=http://127.0.0.1:1/ NO_PROXY= \
    forge-cli install forge-doctor-data --method registry --offline --yes
└  ✅ instalação registry-first concluída
$ .../forge-doctor-data/venv/bin/forge-doctor-data --version
forge-doctor-data 1.0.0
```

Receipt da instalação offline: `"source": "cache"`,
`"resolvedVia": "offline-cache"`, `verify.ok:true`. O resolve leu
`cache/pypi/forge-doctor-data.json` (versão 1.0.0 sem rede — provado
pela recusa D1 no dist sem cache) e o pip consumiu só `--find-links`
local sob proxies mortos.

Veredito D: **VERIFIED** — instalação 100% offline real por cache +
`--no-index`; lockfile de fecho (`registry lock`) não existe no artefato
publicado (só em HEAD) — registrado como lacuna de release, não de
design.

## E — MCP

```text
$ forge-cli mcp
●  ✅ forge-doctor-data: .../venv/bin/forge-doctor-data mcp
●  ✅ spark-forge-aws: .../venv/bin/sparkforge-aws mcp serve
▲  the-forge: sem mcp_command

$ forge-cli mcp --verify --json
forge-doctor-data: ok, levels=[MCP_INITIALIZED, TOOLS_DISCOVERED],
  tools=14, server=forge-doctor-data/1.0.0, protocol=2024-11-05
spark-forge-aws:  FALHA — stdout-non-json: server escreveu não-JSON no
  stdout (logs indevidos?)
the-forge: sem mcp_command
```

Causa da falha do sparkforge-aws: a dist base **não inclui o extra
`[mcp]`** — `sparkforge-aws mcp serve` imprime um receipt JSON
não-JSON-RPC (`SF-MCP-SDK: SDK do MCP nao instalado...`). Após
`pip install 'sparkforge-aws[mcp]'` na venv: verify passa,
**tools=146**, protocolo 2024-11-05.

tools/call real (stdio JSON-RPC manual, mesmo bin da venv):

```text
INIT  → serverInfo {forge-doctor-data, 1.0.0}
tools/call get_host_status → hosts reais detectados (claude 2.1.295…)
tools/call sparkforge_aws_pack_list  → {installed_core: 0.5.0, ...}
tools/call sparkforge_aws_rules_lookup id=["SF-WASTE-001"] → regra real
```

Ressalvas: `--verify` do 0.2.0 para em `TOOLS_DISCOVERED` — não chama
tools/call (allowlist `mcp_safe_tools` é HEAD-only); `clientInfo` do
handshake está hardcoded `version: "0.1.0"` no dist publicado. Lacuna de
integração: o install registry não puxa o extra `[mcp]` mesmo com
`mcp_command` declarado no catálogo — verificado e contornado
manualmente.

Veredito E: **VERIFIED** com ressalvas acima.

## F — Host (registro MCP real + preservação)

Host exercido: **claude** (adapter `merge-json` em `~/.claude.json`).
`~/.claude.json` pré-semeado com chaves de usuário:

```json
{"userKey":"keep-me","mcpServers":{"user-server":{"command":"/usr/bin/true","args":["--user-owned"]}},"customSection":{"nested":[1,2,3]}}
```

```text
$ forge-cli hosts plan claude forge-doctor-data
- merge-json ~/.claude.json <venv>/forge-doctor-data mcp — mcpServers
  Comando para executar no host: claude mcp add forge-doctor-data --scope user -- .../forge-doctor-data mcp
●  Nada foi escrito — reexecute com --yes para aplicar

$ forge-cli hosts register claude forge-doctor-data --yes
◆  ✅ integração registrada: /tmp/forge-e2e-matrix/home/.claude.json
●  Backup em: ~/.forge-cli/backups/hosts-claude-20261017-215827621

# .claude.json resultante: mcpServers = {user-server, forge-doctor-data};
# userKey e customSection intactos.

$ forge-cli hosts validate claude forge-doctor-data
config-file: pass · mcp-key: pass (forge-doctor-data) · command: pass

$ forge-cli hosts rollback claude forge-doctor-data --yes
◆  ✅ Claude Code: integração revertida
# diff contra o estado pré-register: IDÊNTICO (byte a byte)
```

Veredito F: **VERIFIED**. (`hosts list` travou no mesmo probe
`cursor --version` da perna A — mesmo defeito, não contado duas vezes.)

## G — Portal em Chromium real

Server: `sparkforge-aws portal --no-browser --port 8471` →
`http://127.0.0.1:8471/?forge_session=<token>` ("portal is optional —
CLI/TUI/MCP keep working without it"). Browser: Chromium 148 headless
via playwright do venv `forge-portal/.venv`.

```text
goto /?forge_session=<t>  → 200, redirect p/ /dashboard,
                            cookie forge_session=<t> (HttpOnly,SameSite=Strict)
goto / (cookie-only, sem token na URL) → 200        # o fix recente
curl /api/v1/installation-status sem auth          → 403 PORTAL-SESSION
curl /api/v1/... com Cookie apenas                  → 403 PORTAL-SESSION
curl /api/v1/... com ?forge_session=                → 403 PORTAL-SESSION
curl /api/v1/... com X-Forge-Session: <t>           → 200 (dados reais)
curl /api/v1/... com X-Forge-Session: wrong         → 403
```

Auth real da API é o header `X-Forge-Session`; o cookie é `HttpOnly`
(guarda secundária — SPA mantém o token da URL em memória; por isso o
reload cookie-only serve o documento 200 mas a SPA exibe "Sessão
inválida" sem o token — comportamento coerente, não bug).

Fluxo UI real (uma sessão, sem reload): Instalação → wizard de 9 passos →
`Gerar plano` → **1830 ações planejadas** (skills/agents/mcp, escopo
projeto) → Revisar diff → `Confirmar e executar` → **1482 written,
0 removed, 0 refused, PASS** → Recibo `completed`. Arquivos reais no
workspace: `.claude/agents/*.md` (14 coordinators), `.agents/`,
`.codex/agents/`, `.devin/`, `.github/agents/*.agent.md`, `AGENTS.md`,
receipt `.sparkforge_aws/receipts/install-20261018T010057Z.json`
(`forge/InstallReceipt/v1`, `created_by: sparkforge-aws/0.5.0`) — que
depois alimentou a descoberta da perna M. Lifecycle via UI:
`Desinstalar` → `Confirmar desinstalação` → estado `NOT_INSTALLED`,
arquivos removidos do disco, `uninstall-*.json` gravado; ledger
(`integrations.json` + install receipt) preservado por design.

Notas honestas do adapter: `Atualizar` — "Atualização via portal não é
exposta por este adapter — caminho não verificado"; `mcp-scope:codex` —
NOT_APPLICABLE ("codex nao le .mcp.json de projeto; MCP exige --scope
user"). Hosts detectados no ambiente: claude/devin/codex (healthy),
copilot ausente.

Veredito G: **VERIFIED**.

## H — Forge Lab

```text
$ theforge lab list            → 6 forges declared, modes=A
$ theforge lab collect         → ran=6 skipped=0 failed=0 scenarios=137
    api-forge ok 447ms · forge-doctor-api ok 1976ms · platformforge ok
    2196ms · spark-forge-aws ok 87ms · spark-forge-azure ok 80ms ·
    the-forge ok 17010ms
  report: docs/programs/ecosystem-2026/benchmarks/2026-10-18-A.md
  jsonl:  .../results-2026-10-18-A.jsonl  (forge/BenchmarkResult/v1 strict)
  Guardrails: allow_external=false, env sanitized (sem credenciais),
  jobs=1, mode A, timeout 600s. Descoberta: repos_root=
  /home/edgar/Documentos/projetos/forjas (checkouts irmãos, não as venvs).
```

Especialista (`sparkforge-aws lab`, cwd=checkout do repo):

```text
lab doctor    → docker+compose available, 16cpu/220GB,
                ready:false (version registry ausente no workspace —
                "unresolved_until_host_check" por profile, honesto)
lab scenarios → Golden 20 com fingerprint sha256 + fidelity tier
                (LAB-001 L1 real_local_engine: proves declared_engine_
                semantics; does_not_prove aws_service_semantics)
lab verify    → valid:true, 11 registry components, 20 cenários,
                240 actions, provider_tokens=unresolved_without_host_
                transcript
lab run LAB-001               → execution.status=planned (dry-run default)
lab run LAB-001 --execute --confirm
                            → execution.status=unresolved —
                "runtime execution adapter must be enabled on host"
lab up/down/shell/gc          → mesma fronteira (status planned /
                unresolved_host_execution) — execução real é opt-in do host
```

Interpretador: receipts registram `python: 3.14.7` (mais novo que
satisfaz requires_python) — escolha comprovada por `install.json`.
Extras: `[mcp]` só afeta `mcp serve`; lab idêntico com/sem o extra.

Veredito H: **VERIFIED** — coleta federada real + plano/cenários/verify
reais; execução de cenários é fronteira de host por design (recusada com
`unresolved`, nunca fingida).

## I — Pisos Python (7 dists publicadas)

`requires_python` real do PyPI × interpretador de piso × smoke:

| dist | requires_python | venv floor | bin smoke |
|---|---|---|---|
| theforge-core 0.5.0 | >=3.11 | python3.11 (3.11.16) | `theforge 0.5.0` |
| apiforge-af 0.1.0 | >=3.12 | /usr/bin/python3.12 (3.12.3) | `apiforge 0.1.0` |
| platformforge 0.1.0 | >=3.10 | python3.10 (3.10.21) | `platformforge 0.1.0` |
| sparkforge-aws 0.5.0 | >=3.10 | python3.10 (3.10.21) | `sparkforge-aws 0.5.0` |
| sparkforge-azure 0.1.0 | >=3.10 | python3.10 (3.10.21) | `sparkforge-azure 0.1.0` |
| forge-doctor-data 1.0.0 | >=3.11 | python3.11 (3.11.16) | `forge-doctor-data 1.0.0` |
| forge-doctor-api 0.2.0 | >=3.11 | python3.11 (3.11.16) | `forge-doctor-api 0.2.0` |

Todos os pisos disponíveis (uv `~/.local/bin/python3.1{0,1}` +
`/usr/bin/python3.12`) — nenhum BLOCKED. `pip install <dist>` resolveu a
versão publicada em cada venv do piso exato.

Veredito I: **VERIFIED**.

## J — Fault injection

```text
# J1 — state.json corrompido ("{ CORRUPT-TEST-2")
$ forge-cli registry        → todas as 7 mostradas "—" (não-instaladas)
$ forge-cli status          → "não clonado" ×8; exit 0, sem crash,
                              nunca reporta saudável
→ `.corrupt` quarentenado com os bytes corrompidos preservados
  (observado criado durante a leitura no build publicado — desvio
  menor do comentário em src/registry/install.ts que diz "nunca no
  load"; o efeito é o mesmo: evidência preservada, state não curado
  silenciosamente)

# J2 — uninstall parcial: receipt mantido, venv movido fora
$ forge-cli registry        → ainda lista forge-doctor-data 1.0.0
                              (confia no receipt)
$ forge-cli mcp forge-doctor-data --verify --json
  → ok:false, binPresent:false, "binário MCP ausente na venv"  ← detecta
$ forge-cli reinstall forge-doctor-data --method registry --yes
  → venv recriada, bin `forge-doctor-data 1.0.0` funcional       ← repara
```

Veredito J: **VERIFIED** — degrada fail-safe (ausente, nunca saudável),
quarentena de evidência, detecção de estado parcial e reparo real.

## K — Independência do forge-cli

```text
$ env -i PATH=/usr/bin:/bin:/home/edgar/.local/bin HOME=... bash -c '...'
which forge-cli                         → exit 1 (ausente do PATH)
theforge --version                      → theforge 0.5.0
sparkforge-aws --version                → sparkforge-aws 0.5.0
forge-doctor-data --version             → forge-doctor-data 1.0.0
sparkforge-aws doctor --help            → exit 0
forge-doctor-data --help                → exit 0
```

Veredito K: **VERIFIED** — Forjas instaladas via registry são CLIs
independentes; forge-cli é conveniência, não dependência.

## L — Release pipeline

```text
$ npm view theforge-cli dist
  shasum c97ce21e…806e9 · integrity sha512-uG9asVO1…FT+SA==
  signatures ×2 (keyid SHA256:DhQ8wR5APBvFHLF/+Tc+AYvPOdTpcIDqOhxsBHRwC7U)
  attestations.url …/attestations/theforge-cli@0.2.0
  provenance.predicateType = https://slsa.dev/provenance/v1
$ npm pack theforge-cli → sha512==integrity ✓ · sha1==shasum ✓ · 9 files
$ cd npm/lib/node_modules/theforge-cli && npm audit signatures
  audited 32 packages — 32 verified registry signatures,
  4 verified attestations
$ PyPI three-way: wheel-cache sha256 == pypi.org digest == receipt
  verifiedHash → match=True (theforge-core, sparkforge-aws)
```

Lacuna: as 7 dists PyPI não têm PEP 740 provenance nem assinatura
(`provenance=None`, `has_sig=False`) — só digest sha256 (que o CLI
verifica no install e que confere aqui). npm lado tem SLSA v1 +
sigstore.

Veredito L: **VERIFIED** com a lacuna PyPI registrada.

## M — Multi-Forge (theforge)

```text
$ theforge specialists list        # HOME isolado + PATH só com as venvs
spark-forge-aws  CONFIGURED  v0.5.0  cli:sparkforge-aws
  - install_root missing on disk; cli on PATH is the live install
$ theforge specialists doctor      → idem (probe real)
$ theforge graph
Capability graph: 2 action 2 capability 1 domain 1 provider (5 edges)
  provider:echo-forge → demo.*  (explicit, manifest)
$ theforge capabilities list       → só demo.echo / demo.inspect
$ theforge providers sync          → REFUSED "requires explicit approval"
$ theforge providers sync --yes    → completed; spark-forge-aws blocked:
    "provider adapter metadata is unavailable"
$ theforge task run "echo hello"   → FORGE-USAGE: "no delegable
    specialists — none declare an agentic manifest with executable
    workflows"
$ theforge lab collect             → execução federada real + recibos
    strict-validados (perna H)
```

Dois gaps de integração comprovados (ambos recusados honestamente, nunca
fingidos): (1) o wheel `theforge-core` **não empacota
`forge-knowledge/*.json`** (`knowledge.DEFAULT_KNOWLEDGE_DIR` resolve
fora de site-packages → catálogo de especialistas vazio →
capabilities/ask/task só enxergam echo-forge); (2) o manifest escrito
pelo portal em `~/.forge/installations/spark-forge-aws.json` não carrega
`provider.argv`/module → providers sync o bloqueia. Descoberta por
`installations` registry + probe cli-on-PATH funciona; execução
multi-forge real existiu via `lab collect` (receipts) e via portal
(perna G escreveu o manifest que o theforge descobriu).

Veredito M: **PARTIAL** — discovery/grafo/lab federado verificados;
roteamento por capacidade aos especialistas registry-installed está
funcionalmente bloqueado pelos dois gaps acima.

## N — README público literal

Passos do README de `forge-cli` executados literalmente em subshell
limpo: `npm i -g theforge-cli` ✓ (prefix isolado); `forge-cli` TUI —
menu → Instalar Forjas → preflight → dir default `./forge-workspace` →
seleção 8/8 → plano por repo (origem+comandos) → confirmação → cancel
limpo ✓; `forge-cli clone forge-doctor-data --dir .../clones --yes` →
clone público real em 2.8s, nenhum script ✓; `forge-cli self install`
→ `~/.forge-cli/bin/{forge-cli,index.mjs}` + bloco guardado
`# >>> forge-cli >>>` em `.bashrc`+`.profile`; `self uninstall` →
remove tudo, blocos fora, grep forge=0 ✓.

Lacunas README↔artefato publicado: README afirma que a TUI "abre com
registry como opção recomendada" — o 0.2.0 publicado **não mostra
chooser de método** (vai direto ao plano git-clone; o chooser é
HEAD-only, PR #30); README não documenta `--version` (e ele falha no
publicado, leg A); help do publicado omite `lock`/`heal`/`wizard`/
`profile`/`recover` que o dist executa. Não exercido: `install --method
git` com scripts (`install.sh` mutaria clones do usuário — fora do
isolamento permitido); o caminho nativo foi coberto indiretamente pelo
installer real via portal (perna G).

Veredito N: **VERIFIED** com lacunas de doc registradas.

## Evidência e artefatos locais

- Logs: `/tmp/forge-e2e-matrix/logs/` (A-*.log, B-*.log, G-*, H-*, I-*)
- Snapshots de estado: `/tmp/forge-e2e-matrix/snapshots/state-*.json`
- Receipts: `/tmp/forge-e2e-matrix/home/.forge-cli/forges/*/install.json`,
  `.../forges/state.json`, `.../state.json.corrupt` (quarentena J1)
- Report lab federado: `/tmp/forge-e2e-matrix/docs/programs/
  ecosystem-2026/benchmarks/2026-10-18-A.md` + `results-*.jsonl`
- Receipts portal: `/tmp/forge-e2e-matrix/.sparkforge_aws/receipts/`
  `install-…Z.json`, `uninstall-…Z.json`

## Resumo de achados (fed forward — não edito FINAL-CERTIFICATION nem
gap-register, dono paralelo)

1. `forge-cli doctor`/`hosts list` **hang sem timeout** no probe
   `cursor --version` (Electron shim girando) — `commandOutput` sem
   timeout em utils/system.ts.
2. `theforge-cli@0.2.0` publicado **anterior ao PR #30**: sem
   `--version` self, sem `registry lock`/`--lock`, sem tools/call MCP,
   sem chooser registry-first na TUI; `clientInfo` MCP fixo "0.1.0".
3. Wheel `theforge-core` **não empacota `forge-knowledge/*.json`** →
   catálogo/capabilities/task só enxergam echo-forge numa instalação
   registry pura.
4. Manifest de instalação escrito pelo portal não carrega
   `provider.argv` → `theforge providers sync` bloqueia o especialista.
5. `sparkforge-aws` registry install não puxa extra `[mcp]` → MCP serve
   falha com receipt não-RPC (`SF-MCP-SDK`) até `pip install
   'sparkforge-aws[mcp]'`.
6. `pin` sem `--method` cai no state git-method; `update --check
   --method registry` sem nomes/`--all` diz "nenhuma instalada".
7. PyPI dists sem PEP 740/sig (só sha256 — verificado 3-vias ok); npm
   tem SLSA+sigstore.
8. Comportamento `.corrupt` do state observado já na leitura no build
   publicado (comentário em install.ts fala em write-path apenas) —
   efeito igual: evidência preservada, leitura fail-safe.
