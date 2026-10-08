# Desenvolvimento com agentes

Este guia descreve como trabalhar no repositório com agentes de código (Claude Code, Codex e Devin): onde cada host lê instruções e skills, o workflow Kiro de specs, quais assets são versionados, como manter os mirrors de skills sem drift e como a auditoria de assets agentic funciona. É o destino versionado das regras de workflow que saem de `CLAUDE.md` e `AGENTS.md`; essas instruções guardam só as invariantes do projeto e regras persistentes curtas.

Nada aqui afeta o runtime: o pacote `theforge` nunca lê, inclui nem requer os assets agentic ([ADR 0020](adr/0020-agentic-assets-canonical-source.md)).

## Hosts suportados

| Host | Arquivo de instrução | Diretório de skills | Invocação de skill |
|---|---|---|---|
| Claude Code | [`CLAUDE.md`](../CLAUDE.md) | `.claude/skills/kiro-*/SKILL.md` | `/kiro-<nome>` |
| Codex | [`AGENTS.md`](../AGENTS.md) | `.agents/skills/kiro-*/SKILL.md` (agentes customizados em `.codex/agents/`) | `$kiro-<nome>` |
| Devin Local / CLI | [`AGENTS.md`](../AGENTS.md) | `.devin/skills/kiro-*/SKILL.md` | `/kiro-<nome>` |

- Codex e Devin leem o mesmo `AGENTS.md`; o Claude Code lê só `CLAUDE.md`.
- Cada skill é um diretório com um `SKILL.md` e, quando precisa, arquivos de apoio (`rules/*.md`, `templates/*.md`). As skills rodam inline, com acesso ao contexto da conversa, e podem delegar pesquisa paralela a subagentes. Arquivos adicionais (templates, exemplos) podem ser acrescentados ao diretório da skill.
- No Codex, `/skills` lista as skills disponíveis; cada skill tem ainda `agents/openai.yaml`, metadado do host.
- As mesmas 17 skills `kiro-*` existem nos três hosts. Três delas são protocolos usados por outras: `kiro-review` (revisão adversarial local à tarefa, usada pelos subagentes revisores), `kiro-debug` (depuração pela causa raiz, usada pelos subagentes de debug) e `kiro-verify-completion` (evidência fresca antes de declarar sucesso ou conclusão).

### Uso das skills
- Use as skills pedidas explicitamente pelo usuário e as relevantes ao domínio da tarefa, inclusive design, acessibilidade e UX.
- Escolha as skills primeiro pela descrição ou pelos metadados; depois leia só as skills escolhidas e as referências necessárias para a tarefa.
- Siga as regras explícitas do host e do projeto e mantenha as checagens exigidas pelo workflow. Não pule uma skill relevante só porque a tarefa é pequena.

### Subagentes e delegação
- **Codex:** as versões atuais habilitam subagentes por padrão, sem flag experimental; um administrador ou usuário pode desativá-los com `enabled = false` em `[agents]` na configuração do Codex. Use delegação quando o usuário, as regras do projeto ou o workflow da skill pedirem. A revisão cross-spec do `kiro-spec-batch` usa o agente customizado `.codex/agents/spec-reviewer.toml` quando disponível.
- **Devin Local / CLI** (Devin Desktop e Devin CLI; o Devin Cloud não é configurado): os controladores de workflow rodam na conversa principal. Use `run_subagent` e `read_subagent` com os esquemas atuais do runtime: `subagent_general` para implementação, revisão que roda testes e depuração; `subagent_explore` é só leitura e não implementa. Prefira workers em primeiro plano quando um comando puder pedir aprovação (workers em segundo plano não pedem permissões novas); trate uma permissão negada pelo fluxo de aprovação do host, sem desativar permissões nem conceder ferramentas automaticamente. Subagentes nativos não delegam de novo por padrão: a orquestração fica no agente principal, e um worker de batch executa inline as skills de fase e as revisões exigidas quando não puder delegar. Subagentes da CLI podem estar desativados por configuração ou política; o Devin Desktop expõe a opção Subagents (Preview).
- **Em todos os hosts:** dê a cada implementador e revisor independente um contexto novo, com o checkout exato, os caminhos absolutos de entrada e as instruções relevantes à tarefa; espere o resultado antes da revisão ou da conclusão da tarefa; mantenha sequenciais os agentes que escrevem no repositório. Se a delegação não estiver disponível, siga o fallback inline da skill e identifique a revisão como inline, não como independente. Descobrir uma skill não prova que um subagente rodou nem que houve revisão independente.

## Workflow Kiro

Desenvolvimento orientado a specs no estilo Kiro, num SDLC agentic.

### Steering e specs
- **Steering** (`.kiro/steering/`): memória de projeto, fonte de verdade de longo prazo para padrões, convenções e decisões; regras e contexto do projeto inteiro para guiar os agentes (princípios de arquitetura, nomes, restrições de segurança, decisões de stack, padrões de API). Arquivos padrão: `product.md`, `tech.md` e `structure.md`; arquivos customizados são gerenciados por `kiro-steering-custom`.
- **Specs** (`.kiro/specs/<feature>/`): formalizam o desenvolvimento de cada feature (`requirements.md`, `design.md`, `tasks.md`, `research.md`, `spec.json`); as notas de cada spec ficam com ela e guiam os workflows de especificação.
- Para trabalho de spec e de implementação, carregue os arquivos de steering padrão de `.kiro/steering/`, reaproveitando o contexto atual em vez de reler arquivos que não mudaram. Carregue steering adicional só quando as regras do projeto exigirem ou quando for relevante à tarefa. Mantenha o steering atualizado e confira o alinhamento com `kiro-spec-status`.
- Arquivos `AGENTS.md` locais (por exemplo `src/<pasta>/AGENTS.md`) podem descrever premissas de domínio, contratos ou convenções de teste de uma pasta; Codex e Devin os carregam ao trabalhar naquele caminho.
- As specs ativas estão em `.kiro/specs/`; o progresso de cada uma é visto com `kiro-spec-status <feature>`.

Neste repositório `.kiro/specs/` e `.kiro/steering/` são locais e não versionados (ver [Assets versionados e locais](#assets-versionados-e-locais)); hoje o steering local tem só `roadmap.md`. As skills funcionam sem steering.

### Fases
Os comandos abaixo usam a sintaxe do Claude e do Devin (`/kiro-…`); no Codex o prefixo é `$kiro-…`.

- Fase 0 (opcional): `/kiro-steering`, `/kiro-steering-custom`.
- Discovery: `/kiro-discovery "ideia"` decide o caminho e escreve `brief.md` e `roadmap.md` para projetos com várias specs.
- Fase 1 (especificação):
  - Uma spec: `/kiro-spec-quick <feature> [--auto]`, ou passo a passo: `/kiro-spec-init "descrição"` → `/kiro-spec-requirements <feature>` → `/kiro-validate-gap <feature>` (opcional, para código existente) → `/kiro-spec-design <feature> [-y]` → `/kiro-validate-design <feature>` (opcional, revisão de design) → `/kiro-spec-tasks <feature> [-y]`.
  - Várias specs: `/kiro-spec-batch` cria todas as specs do `roadmap.md` em paralelo, por onda de dependência.
- Fase 2 (implementação): `/kiro-impl <feature> [tarefas] [--review required|inline|off]`.
  - Sem números de tarefa: modo autônomo (um subagente por tarefa, revisão independente e validação final).
  - Com números de tarefa: modo manual (as tarefas escolhidas no contexto principal, ainda com revisor antes da conclusão).
  - `--review off` pula a revisão local da tarefa; use de propósito e mantenha `/kiro-validate-impl <feature>` como gate final de qualidade.
  - `/kiro-validate-impl <feature>` revalida a feature isoladamente.
- Progresso: `/kiro-spec-status <feature>`, a qualquer momento.

### Regras de desenvolvimento
- Aprovação em 3 fases (*3-phase approval workflow*): Requirements → Design → Tasks → Implementation.
- Revisão humana em cada fase; use `-y` só para fast-track intencional.
- Siga as instruções do usuário com precisão e, dentro desse escopo, aja com autonomia: reúna o contexto necessário e conclua o trabalho pedido de ponta a ponta na mesma execução, perguntando só quando faltar informação essencial ou as instruções forem criticamente ambíguas.
- Idioma: pense em inglês e responda em português. Todo Markdown escrito em arquivos de spec (por exemplo `requirements.md`, `design.md`, `tasks.md`, `research.md` e relatórios de validação) usa o idioma configurado na spec (`spec.json.language`).

## Assets versionados e locais

| Versionados (rastreados pelo git) | Locais (fora do git) |
|---|---|
| `.claude/skills/kiro-*`, `.agents/skills/kiro-*`, `.devin/skills/kiro-*` | `.kiro/specs/` |
| `agentic/skills/forge-*.md` (canônicas) + mirrors renderizados nos três hosts | `.kiro/steering/` (inclui `roadmap.md` e os eventuais `product.md`, `tech.md`, `structure.md`) |
| `agentic/agents/*.toml` (canônicos) + `.codex/agents/*.toml` (render) | `.claude/agents/` |
| `.kiro/settings/` (cópias de referência de regras e templates) | `.agents/skills/source-command-*` e outros scaffolds de terceiros |
| `forge-knowledge/*.json` (pacotes de bootstrap dos seis especialistas) | |
| `factory/specs/` + `factory/templates/` (fila Loop Factory — a pasta é o estado, [docs/loop-factory.md](loop-factory.md)) | `factory/prompts/`, `factory/runs/`, `factory/reviews/`, `factory/logs/` (artefatos gerados) |
| `CLAUDE.md`, `AGENTS.md` | |
| `scripts/agentic/` (auditoria, renderers e configuração) | |

Specs e steering ficam locais por decisão do mantenedor: são material de trabalho de cada ciclo, e as regras persistentes do projeto vivem em `CLAUDE.md`, `AGENTS.md` e `docs/`. Nenhuma verificação, documento versionado ou instrução de host depende dos assets locais; a auditoria lê só arquivos rastreados, e a suíte offline dá o mesmo resultado com ou sem eles. Não crie links de documentos versionados para `.kiro/`.

## Manutenção dos mirrors

Duas famílias, dois regimes:

- **`kiro-*`**: mantidas à mão nos três hosts, protegidas por auditoria ([ADR 0020](adr/0020-agentic-assets-canonical-source.md)).
- **`forge-*` + agentes**: fonte canônica em `agentic/skills/` e `agentic/agents/`; os mirrors são **gerados** por `render_skills.py` e `render_agents.py` — edite a fonte, rode o renderer, nunca toque o mirror ([ADR 0056](adr/0056-agentic-host-adaptation.md), [docs/skills.md](skills.md), [docs/agents.md](agents.md)). A camada de conhecimento que as skills referenciam vive em `forge-knowledge/` ([docs/forge-knowledge.md](forge-knowledge.md)).

1. **`kiro-*` — edite os três hosts na mesma mudança.** Uma mudança em `SKILL.md` ou num arquivo de apoio vai para `.claude/skills/`, `.agents/skills/` e `.devin/skills/` juntas, ajustando só a sintaxe de cada host (prefixo `/kiro-` ou `$kiro-`, frontmatter, termos de delegação).
2. **Rode a auditoria** e corrija até ela sair com 0:

   ```
   python scripts/agentic/audit_assets.py            # relatório em texto
   python scripts/agentic/audit_assets.py --json     # relatório em JSON (chaves ordenadas)
   ```

   Opções: `--root DIR` (raiz do repositório; padrão: este repositório) e `--config FILE` (padrão: [`scripts/agentic/agentic.toml`](../scripts/agentic/agentic.toml)). Saída 0 sem achados de falha, 1 com achados de falha, 2 para erro de configuração ou de git. A ferramenta só lê arquivos rastreados pelo git, não escreve nada e não usa rede; arquivos novos só entram na auditoria depois de `git add`.
3. **Corrija drift no mirror divergente** sempre que a diferença mudar o comportamento do agente. Registre como aceita só a diferença de fraseado.

### Categorias de achados

| Categoria | Falha? | Significado |
|---|---|---|
| `host-syntax` | não | texto difere, perfil semântico igual; ou metadado de host declarado (`host_metadata`) |
| `accepted` | não | divergência registrada em `[[accepted]]`, mostrada com o motivo |
| `host-only` | não | asset exclusivo declarado em `[[host_only]]` |
| `drift` | sim | um elemento do perfil (nome, caminhos referenciados, skills referenciadas, fases de `spec.json`, arquivos de apoio) diverge entre hosts |
| `missing-skill` | sim | skill ausente num host |
| `support-drift` | sim | arquivo de apoio diverge entre hosts ou da cópia de referência em `.kiro/settings/rules/` além dos placeholders de instalação |
| `host-only-undeclared` | sim | arquivo rastreado de diretório de host fora de uma skill equivalente e não declarado |
| `stale-accepted` | sim | entrada `[[accepted]]` que não corresponde a nenhuma divergência atual: remova a entrada |
| `invariants`, `budget`, `pointer`, `moved-rule` | sim | checagens das instruções de host, ativas quando a seção correspondente está declarada |
| `skill-quality` | sim | fonte canônica `agentic/skills/` sem descrição/seções de limites, freshness divergente do pacote `forge-knowledge`, ou ref de invocação morta |

O perfil semântico tolera cabeçalhos, envelopes, prefixos de invocação e a forma do argumento da feature (`$1`, `$ARGUMENTS`, `{feature-name}`); a contrapartida é que prosa divergente sem efeito em nenhum elemento do perfil passa sem achado.

### Como aceitar uma divergência
Acrescente a [`agentic.toml`](../scripts/agentic/agentic.toml) uma entrada com os valores exatos do achado `drift` (skill, elemento, hosts que têm o valor e o valor) e um motivo concreto, que diga por que o comportamento não muda:

```toml
[[accepted]]
skill = "kiro-spec-quick"
element = "paths"
hosts = ["codex", "devin"]
value = ".kiro/specs/{feature}/design.md"
reason = "só o texto do resumo final exibido ao usuário; ..."
```

Motivo vazio é erro de configuração (saída 2). Quando a divergência some, a entrada vira `stale-accepted` e precisa ser removida, então o registro nunca fica desatualizado. Asset exclusivo de um host vai em `[[host_only]]` (`path`, `host`, `reason`); metadado por skill de um host vai em `host_metadata` do host; substituição feita pelo instalador nas cópias de regras (hoje o idioma em `spec.json.language`) vai em `[[install_placeholders]]` (`pattern`, `replacement`).

### Depois de reinstalar o instalador Kiro
Reinstalar o instalador upstream é permitido para atualizar os fluxos, mas reescreve os mirrors e reconcatena os blocos de `AGENTS.md`. Depois de reinstalar:

1. remova de novo os comandos legados se reaparecerem em `.claude/commands/` (ver [Comandos legados](#comandos-legados));
2. restaure `CLAUDE.md` e `AGENTS.md` curtos, com o bloco de invariantes e os ponteiros (use o histórico git);
3. revise o diff dos mirrors, rode a auditoria e atualize `agentic.toml` (novas skills, metadados, aceitas obsoletas) até ela sair com 0.

## Invariantes nas instruções de host
As invariantes do projeto ficam num bloco único, delimitado por `<!-- theforge:invariants:begin -->` e `<!-- theforge:invariants:end -->`, com texto idêntico em `CLAUDE.md` e `AGENTS.md`. Para mudá-las (inclusive os comandos de setup, teste, lint, tipos ou regeneração de schemas), edite o bloco nos dois arquivos na mesma mudança e atualize as âncoras de `[invariants]` em `agentic.toml`. Quando `[invariants]` está declarada, a auditoria falha se o bloco faltar num arquivo, divergir entre os arquivos ou perder uma âncora obrigatória.

## Orçamentos de tamanho
As instruções sempre carregadas são curtas para economizar contexto em cada sessão:

| Arquivo | Orçamento |
|---|---|
| `CLAUDE.md` | 2 500 bytes |
| `AGENTS.md` | 6 000 bytes |

O tamanho é medido em bytes UTF-8 com fins de linha LF. Detalhe de workflow vai para este guia ou para as skills, não para as instruções. Cada regra que sai das instruções é registrada em `[[moved_rules]]` de `agentic.toml` com o destino; com `[budgets]` e `[[moved_rules]]` declarados, a auditoria falha para arquivo acima do orçamento e para regra movida ausente no destino.

## Comandos legados
Os 11 comandos `.claude/commands/kiro/` (invocados como `/kiro:<nome>`) foram removidos: eram duplicatas só do Claude, de uma geração anterior, sem os review gates das skills. Use a skill equivalente:

| Comando removido | Skill |
|---|---|
| `/kiro:spec-init` | `kiro-spec-init` |
| `/kiro:spec-requirements` | `kiro-spec-requirements` |
| `/kiro:spec-design` | `kiro-spec-design` |
| `/kiro:spec-tasks` | `kiro-spec-tasks` |
| `/kiro:spec-impl` | `kiro-impl` |
| `/kiro:spec-status` | `kiro-spec-status` |
| `/kiro:steering` | `kiro-steering` |
| `/kiro:steering-custom` | `kiro-steering-custom` |
| `/kiro:validate-gap` | `kiro-validate-gap` |
| `/kiro:validate-design` | `kiro-validate-design` |
| `/kiro:validate-impl` | `kiro-validate-impl` |

## Política de hooks
O repositório não versiona hooks de desenvolvimento. Se forem adicionados (hooks de edição de um host ou pre-commit), rodam só checagens focadas e determinísticas sobre os arquivos alterados: `ruff check` nos arquivos tocados, os testes relevantes à mudança, a paridade de schemas quando `src/theforge/contracts/` muda e a auditoria agentic quando assets agentic ou instruções de host mudam. Nunca rodam a suíte completa a cada edição, nunca acessam a rede nem dependem de providers reais, credenciais ou assets locais, e não substituem o CI. Detalhes no [ADR 0020](adr/0020-agentic-assets-canonical-source.md).

## Capability × skill × MCP tool × comando de host

O ciclo 3 avaliou a compatibilidade conceitual do Forge com os formatos dos hosts (ciclo 3, wave L) sem converter nada: são planos distintos, e confundi-los quebraria as invariantes.

| Conceito | O que é | Quem o lê | Vida |
|---|---|---|---|
| **Forge capability** | capacidade declarada no manifest de um provider, roteada deterministicamente e executada via Forge Protocol (subprocess + JSON) | o core (`route`) | versionada no manifest, validada por `describe`/`health`, auditável por run |
| **Agent Skill** (`kiro-*`) | instruções em Markdown que dirigem o *comportamento do agente* dentro de um host | o agente, no host | asset versionado, paridade entre mirrors auditada |
| **MCP tool** | ferramenta exposta ao agente por um servidor MCP | o agente, via configuração do host | descoberta na config MCP do host, fora do git deste repositório |
| **Comando de host** (`/kiro-…`, `$kiro-…`) | invocação de uma skill no CLI do host | o host | sintaxe de cada host |

- Uma capability **não é** uma skill: não é Markdown, não orienta a conversa — é um contrato com ops verificáveis e resultado auditável. Uma skill **não é** uma capability: não declara sinais roteáveis nem responde `describe`/`health`.
- Pontos de encontro legítimos, sempre como adaptação e nunca como substituição: uma skill pode orientar o agente a rodar `theforge …`; um servidor MCP poderia embrulhar a CLI do Forge como ferramenta do agente. O provider e o routing permanecem atrás do Forge Protocol.
- Outros hosts entram pelo mesmo contrato: um arquivo de instrução curto com o bloco de invariantes, um diretório de skills declarado em `agentic.toml` e a auditoria no caminho da mudança. Um quarto host com diretório próprio é justamente um dos gatilhos que reabrem o ADR 0020 (fonte canônica renderizada).

## MCP Registry como referência

O registry oficial do MCP foi avaliado como inspiração para discovery/lifecycle (ciclo 3, wave L), sem adoção automática: os dois registram coisas diferentes — o registry MCP descobre *servidores que equipam o agente*; o Forge Registry descobre *providers que executam trabalho*.

- **O que a comparação confirma já coberto:** o Forge Registry já tem o equivalente local do que um registry remoto oferece — identidade versionada (manifest `id`+`version`), lifecycle por estado (`ready`, `broken`, `changed`, `unreachable`), capacidades declaradas (`capabilities`), e health verificado por chamada real em vez de metadado declarado.
- **O que inspiraria, se um dia existir catálogo remoto de providers:** publicação de manifests como pacotes com nome e versão, indexação por capability id e um receipt de ingestão — sempre como *índice opt-in separado*, nunca como fonte de verdade do registry local, e nunca executado sem o mesmo funil de trust/policy de um provider local.
- **Não-objetivo explícito:** o Forge continua offline-first — `registry refresh` lê manifests locais e roda `health`; nenhuma descoberta de capability depende de MCP, de rede ou de um catálogo remoto.
