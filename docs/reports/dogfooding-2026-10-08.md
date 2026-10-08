# Dogfooding — 2026-10-08: primeira sessão real no próprio repositório

Sessão de dogfooding conforme [`docs/dogfooding.md`](../dogfooding.md): The
Forge 0.4.0 (branch `devin/cycle52-docs-hardening`) usado de verdade sobre o
próprio checkout `E:\projetos\the-forger`, com os **seis especialistas reais**
registrados no providers.toml do usuário (`trust = "local"`).

## Setup observado

```text
theforge init                      # cria .forge/ (config, runs, cache)
registry refresh                   # describe + fingerprint dos seis
providers health                   # 6/6 ready/ok
```

Primeira tentativa com `[[providers]]` em `.forge/config/providers.toml`:
o core ignorou `trust = "local"` (providers de projeto são sempre
`unverified`) e recusou o describe — deny-by-default correto, com mensagem
açãoável apontando o providers.toml do usuário. Movido para
`%APPDATA%\theforge\providers.toml`: os seis ficaram `ready`.

## Runs reais

| run_id | comando | resultado |
|---|---|---|
| `20261008T111639Z-8b7a0cc6` | `ask "analyze the GitHub Actions workflows for this repository" --capability gha.analyze` | `ok` — 5 facts `cicd.github_workflow`, artifact `native/gha-facts.json`, 498 ms, 26 290 context bytes |
| `20261008T112014Z-d51ea4b8` | `ask "scan this repository for secrets" --capability secrets.scan` | `ok` — `facts: 0`, artifact `native/secrets-report.json` |

`explain` do run `gha.analyze`: `Integrity ok (10 checked)`, verificação
`minimal`, limitações honestas (`no workspace descriptor`,
`context-not-reverified`), reproducibilidade `partially_reproducible`
declarada com o motivo — nenhum claim inflado.

## Observações (taxonomia de dogfooding.md §72)

### O1 — evidência perde binding quando basenames colidem entre ruído do repo

```text
type: unexpected cost
context: ask --capability gha.analyze na raiz do the-forger (14 diretórios
         .pytest_tmp* residuais de basetemp do pytest presentes)
expected: cada fact de workflow vinculado ao sha256 do arquivo estagiado
observed: 4/5 facts vinculados; o fact de ci.yml ficou sem location/hash
evidence: run 20261008T111639Z-8b7a0cc6 — context.json mostra três ci.yml
          estagiados (.github/workflows/ci.yml + 2 fixtures em .pytest_tmp_*)
severity: friction
```

O adapter comportou-se corretamente (basename ambíguo → `None`, nunca um
chute). A causa real é poluição: restos de `--basetemp` do pytest entraram no
ContextPack (`max_files`, `no_signal: 19991` não-matching). Ação tomada:
limpeza dos `.pytest_tmp*` residuais; a higiene de basetemp do projeto fica
registrada aqui — não vale a pena especializar `IGNORED_DIRS` para uma
convenção local (seria hardcode de projeto no core).

### O2 — `secrets.scan` nunca vê os arquivos que seu nome sugere

```text
type: documentation gap
context: ask --capability secrets.scan na raiz do the-forger
expected: varredura incluindo arquivos .env/keys
observed: ok com facts: 0; os .env dos fixtures foram excluídos pelo core
          (reason "secret") antes do staging
evidence: run 20261008T112014Z-d51ea4b8 — context.json excluded list
severity: note
```

É a fronteira fazendo seu trabalho: nomes secretos nunca entram no
`work/stage/` do provider. O gap era semântico/documental — `ok/0 facts`
lia-se como "repo limpo". Resolvido neste commit: documentado em
`real-providers.md` **e** declarado no `limitations` do manifest do adapter
(`secrets.scan reads staged content only: …`), para que o consumidor veja o
limite na superfície e não só na documentação. A decisão de produto oposta —
deixar o scan receber nomes-secretos — enfraqueceria a fronteira e segue
proibida sem ADR.

### O3 — trust de provider de projeto é ignorado e isso está certo

```text
type: friction
context: registry refresh com providers no .forge/config/providers.toml
expected: trust="local" respeitado
observed: warning claro por provider + untrusted + instrução exata
evidence: saída do registry refresh
severity: note
```

Deny-by-default com correção guiada. Friction mínima e honesta; nada a mudar.

### O4 — scan da workspace custa ~45 s num repo de ~20k arquivos

```text
type: slow path
context: telemetry do run gha.analyze (profile=economy)
observed: scan=45016ms contra routing=357ms, context=447ms, provider=498ms
severity: note
```

O scan domina o custo de wall time em workspace grande frio; já há hot-paths
medidos em `docs/performance.md`. Sem regressão declarada — registrado como
observação de ordem de grandeza.

### O5 — stale: tabela "níveis de real" listava quatro pacotes

```text
type: documentation gap
context: docs/real-providers.md, linha specialist-real
observed: citava sparkforge-aws/apiforge/forge-doctor-*, omitindo os dois novos
severity: note — corrigido neste commit
```

## Positivos verificados (não são observações — são provas)

- Routing determinístico: `--capability gha.analyze` selecionou
  `platform-forge` com `confidence.level=high`, `requested_capability` como
  sinal medido, sem fallbacks.
- Hash binding real: evidência `PF-CICD-*:file:*` carrega o sha256 verificado
  do arquivo estagiado, nunca um valor reportado pelo especialista.
- Recusa honesta de execução para providers `unverified` — o gate de trust é
  real, não cosmético.
- `explain` reproduz e confere a cadeia de hashes (`Integrity ok`),
  declarando `partially_reproducible` com os motivos.

## Pendências registradas (não decididas nesta sessão)

- Se o ContextPack deve ganhar uma forma de excluir convenções de scratch
  de teste (`.pytest_tmp*`) — hoje `IGNORED_DIRS` cobre só diretórios
  canônicos de ferramenta, e qualquer árvore suja polui a seleção.
