# Research & Design Decisions — agentic-maintainability (Wave E)

## Summary
- **Feature**: `agentic-maintainability`
- **Discovery Scope**: Extension (light discovery). Nenhuma biblioteca nova; o trabalho é ferramenta de manutenção, documentação e instruções de host. Nenhuma mudança no runtime `theforge`.
- **Key Findings**:
  - Os SKILL.md dos três mirrors (`.claude/skills`, `.agents/skills`, `.devin/skills`) diferem muito em texto bruto (cabeçalho, envelopes `<background_information>`/`<instructions>`, `$1`/`$ARGUMENTS`/`{feature}`, `/kiro-`/`$kiro-`, "Agent tool"/"sub-agent"), mas um **perfil semântico** (nome, caminhos referenciados, skills referenciadas, fases de `spec.json`, arquivos de apoio) coincide em 15 de 17 skills; as 2 divergências restantes são de fraseado em texto de saída. Comparação textual normalizada é inviável; comparação por perfil é viável e estável.
  - Os arquivos de apoio (`rules/*.md`, `templates/*.md`) são idênticos byte a byte nos três hosts. Contra as cópias de referência versionadas em `.kiro/settings/rules/`, só `ears-format.md` difere, e a diferença é a substituição de placeholder de instalação (`spec.json.language` / `en` → `pt`).
  - `.claude/commands/kiro/` (11 comandos) é uma geração antiga dos mesmos fluxos: não referencia `brief.md`, nem os review gates (`requirements-review-gate.md`, `design-review-gate.md`), e lê regras de `.kiro/settings/rules/` em vez de `rules/` da skill. Cada comando tem skill equivalente no Claude (`spec-impl` ↔ `kiro-impl`). Na sessão, ambos aparecem listados (`kiro:spec-design` e `kiro-spec-design`), duplicando contexto e oferecendo um caminho sem review gate.

## Research Log

### Inventário de assets agentic versionados
- **Context**: Requisito 1 (auditoria) e 10.3/10.4 (independência de assets locais).
- **Sources Consulted**: `git ls-files`, `git status --porcelain --ignored`.
- **Findings**:
  - Versionados: `.claude/skills/kiro-*` (17), `.claude/commands/kiro/*.md` (11), `.agents/skills/kiro-*` (17, com `agents/openai.yaml` por skill, metadado só do Codex), `.devin/skills/kiro-*` (17), `.codex/agents/spec-reviewer.toml` (agente de revisão cross-spec usado pelo `kiro-spec-batch` no Codex), `.kiro/settings/{rules,templates}`, `CLAUDE.md`, `AGENTS.md`.
  - Não versionados por decisão do mantenedor: `.kiro/specs/`, `.kiro/steering/`, `.claude/agents/` (scaffold AgentSpec), `.agents/skills/source-command-kiro-steering*`. `.claude/sdd/` existe só com diretórios vazios.
  - `.kiro/settings/` **é** versionado; `.kiro/specs/` e `.kiro/steering/` não.
- **Implications**: a auditoria precisa enumerar só arquivos rastreados (`git ls-files`), senão os diretórios `source-command-*` locais apareceriam como "skill presente em um host só" e o resultado dependeria da máquina. Nenhum documento versionado pode linkar `.kiro/specs/` ou `.kiro/steering/`.

### Diferenças entre mirrors de skills
- **Context**: Requisito 2 (paridade tolerante a sintaxe de host).
- **Sources Consulted**: `diff -r` entre os mirrors; protótipo de perfil semântico em Python (scratchpad).
- **Findings**:
  - Diferenças de sintaxe recorrentes: chaves de frontmatter (`allowed-tools`, `argument-hint`, `metadata` só no Claude; `description` às vezes reescrita), envelopes XML, forma do argumento (`$1`, `$ARGUMENTS`, `{feature}`, `{feature-name}`), prefixo de invocação (`/kiro-`, `$kiro-`), termos "Agent tool"/"subagent"/"sub-agent", seções específicas (ex.: "Devin Local / CLI Delegation").
  - Perfil semântico divergente após normalização: `kiro-spec-quick` (Codex/Devin citam `.kiro/specs/{feature}/design.md` e `tasks.md` no texto de saída; o Claude cita `specs/{feature}/…` sem o prefixo) e `kiro-steering` (Codex/Devin citam `.kiro/specs/` numa nota de estilo). Ambos são fraseado, não comportamento.
  - `kiro-spec-status` usa `$ARGUMENTS` no Claude e `{feature}` nos outros: some com a normalização de placeholder.
- **Implications**: o teste compara perfis, não texto. Divergências de fraseado entram num registro de divergências aceitas, cada uma com justificativa, e o teste falha se uma entrada aceita deixar de existir (o registro não apodrece).

### Arquivos de apoio e cópias de referência
- **Context**: Requisitos 1.4 e 2.4.
- **Findings**: `rules/*` e `kiro-impl/templates/*` idênticos nos três hosts. `.kiro/settings/rules/ears-format.md` tem `` `spec.json.language` / `en` `` onde as skills têm `pt` (placeholder do instalador). Os templates de `kiro-impl` não têm cópia em `.kiro/settings/` (comparação só entre hosts).
- **Implications**: normalização explícita e listada de placeholders de instalação; qualquer outra diferença é drift.

### Instruções de host
- **Context**: Requisitos 3 e 4.
- **Findings**:
  - `CLAUDE.md` (5 033 bytes): ~1 KB de regras do Forge (invariantes, comandos, mais contexto) + ~4 KB de instruções Kiro genéricas (paths, minimal workflow, skills structure, development rules, steering configuration).
  - `AGENTS.md` (11 233 bytes): dois blocos de instalador concatenados (Codex e Devin), quase idênticos, **sem nenhuma invariante do projeto**. Codex e Devin leem `AGENTS.md`; Claude Code lê `CLAUDE.md`.
  - Os arquivos de steering `product.md`/`tech.md`/`structure.md`, citados como padrão pelas skills, não existem; `.kiro/steering/` é local.
- **Implications**: bloco de invariantes delimitado por marcadores, idêntico nos dois arquivos; orçamento de bytes por arquivo; workflow Kiro movido para `docs/agentic.md` (versionado) com mapa de regras movidas verificado. Steering continua local e fora do escopo (registrado no ADR 0020).

### Arquivos soltos na raiz
- **Findings**: hoje existe `tuple[str` (0 bytes, não versionado); `(3` e `dict[str` citados no brief já não estão presentes. Origem provável: redirecionamento acidental de shell (`> tuple[str`).
- **Implications**: remoção local e teste de nomes de entradas da raiz com padrão `[A-Za-z0-9._-]+`.

### Documentação e ADRs do ciclo
- **Context**: Requisitos 7–9.
- **Sources Consulted**: `docs/`, `docs/adr/0001–0013`, `README.md`, `docs/cli.md`, designs de `real-provider-integration`, `context-intelligence-v2`, `cross-forge-foundation` (seções Boundary Commitments e Revalidation Triggers).
- **Findings**:
  - ADRs existentes cobrem cache do registry (0009), policy (0010), matriz de CI (0011). As specs anteriores entregam 0014 (local dos adapters), 0015 (context intelligence: tiers, fingerprints, TOCTOU), 0016 (git somente leitura), 0017 (taxonomia de capabilities), 0018 (execução multi-provider), 0019 (taxonomia de erros e reprodutibilidade). Falta só a decisão de fonte canônica de assets agentic → ADR 0020. Numeração congelada entre as specs do ciclo: 0014/0017 `real-provider-integration`, 0015/0016 `context-intelligence-v2`, 0018/0019 `cross-forge-foundation`, 0020 esta spec; não há numeração alternativa.
  - Docs novos vindos das specs anteriores: `docs/real-providers.md`, `docs/versioning.md`, `docs/capabilities.md` (B), `docs/performance.md` (C), `docs/errors.md` (D). O README hoje não os indexa e diz "ciclo 2, Wave A". `architecture.md` e `security.md` têm títulos "(ciclos 1 e 2, Wave A)".
  - Exit codes: README e `docs/cli.md` têm a mesma tabela (0,1,2,3,4,5,70,130); a Wave D acrescenta 6 (divergência de integridade: `explain` e `replay --mode verify` com divergência; fora de `EXIT_BY_STATUS`, por isso em `CLI_FIXED_EXITS`) e `planned → 0` em `EXIT_BY_STATUS`. Não há índice de ADRs.
  - `docs/errors.md` (Wave D) é a lista canônica de códigos; as tabelas de códigos de `docs/protocol.md` passam a linkar para ela. A Wave D renomeia o artefato de run `workspace` para `workspace-descriptor`, tem gate de validação após sua tarefa 5 e pode ser dividida em D1 (multi-provider) e D2 (integridade/explain/erros); esta spec revalida a dependência após cada metade.
  - Escopo das invariantes (cross-spec review): stdlib-only, Python ≥ 3.11 e "nunca importar especialistas" valem para o core (`src/theforge`); os adapters da Wave B importam `sparkforge`/`apiforge` e miram os interpretadores dos especialistas (piso 3.10). A redação vale para o que o core persiste; `.forge/runs/<id>/work/` guarda dados do provider fora dessa invariante. O setup de desenvolvimento passa a `python -m pip install -e .[dev] -e ./adapters/sparkforge -e ./adapters/apiforge` (mesmo comando da Wave B para o CI). Bump de `theforge.__version__` exige linha na matriz de `docs/versioning.md` (`test_compat_matrix.py`).
  - Gatilho de revalidação dirigido a esta spec (de `cross-forge-foundation`): mudança em `ExplainReport`, `CODE_FAMILIES`, códigos publicados ou exit codes → revalidar documentação consolidada e automações. Os demais gatilhos das specs anteriores apontam para outras specs; os de documentação de instalação (Wave A, cache do registry) são cobertos pela passada de consolidação.
- **Implications**: esta spec escreve só o ADR 0020 e o índice; verifica a presença dos demais e trata ausência como bloqueio da spec dona. A consolidação corrige resíduos (status, índice, títulos, exit 6 no README) sem reescrever seções técnicas das specs donas.

### Hooks
- **Findings**: não há `.claude/settings.json` versionado nem hooks no repositório. O seed 16.6 é condicional ("where hooks are added").
- **Implications**: nenhum hook é adicionado nesta wave; a política fica documentada (ADR 0020 e `docs/agentic.md`) para quando forem.

### Empacotamento como plugin (contexto externo)
- **Findings** (conhecimento das plataformas, sem dependência nova): Claude Code aceita plugins com `.claude-plugin/plugin.json` contendo `skills/`, `commands/`, `agents/`, `hooks/`; Codex lê skills de `.agents/skills/` (formato SKILL.md com frontmatter) e instruções de `AGENTS.md`; Devin lê `AGENTS.md` e `.devin/skills/`. Um plugin do Claude não serve a Codex nem a Devin, então "plugin" sozinho não elimina mirrors.
- **Implications**: o ADR compara alternativas com esse fato; a recomendação não depende de plugin.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Diff textual normalizado | Normalizar sintaxe e comparar texto | Simples | Os mirrors têm estrutura de seções diferente; quase tudo viraria "drift" ou exigiria normalizadores frágeis | Rejeitado |
| Perfil semântico + registro de aceitas | Extrair elementos com efeito no comportamento e comparar conjuntos | Estável, tolerante a sintaxe, mensagens precisas | Não detecta mudança de prosa que não altera caminhos/fases/skills | Escolhido; limitação registrada |
| Gerar mirrors de fonte canônica agora | Script que renderiza os 3 hosts | Elimina drift na origem | Migração grande sem benefício comprovado; conflita com reinstalação dos instaladores | Proposto no ADR 0020, não executado |

## Design Decisions

### Decision: Paridade por perfil semântico
- **Context**: 2.1, 2.2.
- **Alternatives Considered**: diff textual normalizado; hash de seções; perfil semântico.
- **Selected Approach**: `SkillProfile` = nome do frontmatter, caminhos de repositório referenciados (normalizados), skills referenciadas (normalizadas), valores de fase de `spec.json`, conjunto de arquivos de apoio. Arquivos de apoio comparados byte a byte após normalização de fim de linha e de placeholders de instalação.
- **Rationale**: no protótipo, 15/17 skills coincidem e as 2 diferenças são explicáveis; o perfil captura o que muda o comportamento do agente (o que ele lê, escreve e invoca).
- **Trade-offs**: prosa divergente sem efeito nesses elementos passa; aceitável porque os arquivos de apoio (onde estão as regras de review) são comparados por conteúdo.
- **Follow-up**: confirmar na implementação a lista final de divergências aceitas.

### Decision: Enumeração por `git ls-files`
- **Context**: 1.6, 10.3.
- **Selected Approach**: a auditoria só considera arquivos rastreados; o teste pula com motivo explícito se o `git` não estiver disponível (o CI sempre tem). Chamada com `-c core.fsmonitor=false` e ambiente mínimo, sem escrita.
- **Rationale**: assets locais (`source-command-*`, `.claude/agents/`) não podem mudar o resultado.

### Decision: Ferramenta em `scripts/agentic/`, não no pacote
- **Context**: 5.2, 10.1.
- **Selected Approach**: `scripts/agentic/audit_assets.py` (stdlib, tipado, coberto por mypy/ruff como `scripts/ci/`) + `scripts/agentic/agentic.toml` (configuração declarativa lida com `tomllib`). Testes carregam o módulo pelo caminho, como os testes de `scripts/ci/`.
- **Rationale**: o wheel continua sem os assets e sem código de manutenção; nenhuma dependência nova.

### Decision: Bloco de invariantes com marcadores
- **Context**: 3.1–3.4.
- **Selected Approach**: `<!-- theforge:invariants:begin -->` … `<!-- theforge:invariants:end -->` em `CLAUDE.md` e `AGENTS.md`, texto idêntico (após normalização de fim de linha) e âncoras obrigatórias listadas em `agentic.toml`.
- **Rationale**: igualdade textual é a forma mais simples de garantir "mesmo texto em todos os hosts"; as âncoras garantem que o bloco não fique vazio.

### Decision: Remover `.claude/commands/kiro/`
- **Context**: 4.8; achado de drift semântico (comandos sem review gates).
- **Alternatives Considered**: manter e registrar como exclusivos de host; manter e sincronizar com as skills; remover.
- **Selected Approach**: remover os 11 comandos e documentar a correspondência (`/kiro:spec-X` → `/kiro-spec-X`, `/kiro:spec-impl` → `/kiro-impl`) em `docs/agentic.md`.
- **Rationale**: cada comando tem skill equivalente mais nova; mantê-los oferece um caminho sem review gate e duplica a lista de comandos carregada na sessão.
- **Trade-offs**: quem digita `/kiro:spec-design` precisa passar a usar `/kiro-spec-design`; mitigado pela tabela de correspondência.

### Decision: Orçamentos de tamanho
- **Selected Approach**: `CLAUDE.md` ≤ 2 500 bytes e `AGENTS.md` ≤ 6 000 bytes (UTF-8, fins de linha LF), registrados em `agentic.toml`.
- **Rationale**: o conteúdo Forge atual do CLAUDE.md cabe em ~1,2 KB mais o bloco de invariantes (~1 KB); o AGENTS.md consolidado precisa de seção comum, seção Codex (subagentes) e seção Devin (delegação), estimado em ~5 KB.

### Decision: ADR 0020 e índice de ADRs
- **Selected Approach**: ADR 0020 decide "manter mirrors versionados à mão + paridade testada" agora e registra a proposta de fonte canônica (render a partir de `.kiro/settings` estendido) e a avaliação de plugin, com critério de gatilho; política de hooks incluída. `docs/adr/README.md` lista todos os ADRs e mapeia as 8 decisões exigidas pelo ciclo.

### Generalização (design synthesis)
- Os requisitos 2, 3, 4.3–4.6 e 6 são variações de "invariante estrutural do repositório verificada por teste offline". Interface única: `audit()` retorna `Finding`s tipados por categoria; o teste agrupa por categoria. A higiene da raiz e a consistência de docs ficam em testes próprios porque não são assets agentic (sem generalizar a implementação além disso).

### Build vs. Adopt
- Ferramentas de diff/lint de Markdown (markdownlint, lychee) exigiriam dependência nova ou rede; a verificação de links necessária é só para links relativos locais (regex + `Path.exists`). Construído com stdlib.
- Instalador upstream dos assets Kiro: adotado como origem dos mirrors (não reexecutado nesta wave); o ADR 0020 registra que reinstalar exige rodar a auditoria.

### Simplificação
- Sem classe por host, sem plugin de normalização: uma tabela declarativa (`agentic.toml`) e funções puras.
- Sem novo job de CI: os testes entram na suíte offline existente.

## Risks & Mitigations
- Reinstalar o instalador Kiro reescreve mirrors e reconcatena blocos no `AGENTS.md` — a auditoria falha e `docs/agentic.md` documenta o procedimento de reinstalação (reaplicar o bloco de invariantes e o orçamento).
- Specs anteriores ainda não mescladas quando a consolidação rodar — tarefas de documentação/ADR/relatório dependem da Wave D mesclada; ausência de ADR dono é bloqueio reportado, não ADR redigido por esta spec.
- Fins de linha CRLF no Windows alterariam comparações e tamanhos — toda leitura normaliza para LF antes de comparar ou medir.
- Perfil semântico não pega prosa divergente — arquivos de apoio comparados por conteúdo; limitação documentada no ADR 0020.

## References
- `docs/adr/0008-cli-name.md`, `0009`, `0010`, `0011` — ADRs existentes exigidos pelo ciclo.
- `.kiro/specs/cross-forge-foundation/design.md` — gatilho de revalidação dirigido a esta spec (consulta local; não linkado em docs versionados).
- `tests/test_packaging.py`, `scripts/ci/` — padrão de ferramenta em `scripts/` exercitada por testes.
- `tests/conftest.py` `FILE_MARKERS` — todo arquivo de teste novo precisa de categoria.
