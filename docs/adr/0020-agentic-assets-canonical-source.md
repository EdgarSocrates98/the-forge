# ADR 0020 — Fonte canônica de assets agentic e política de hooks

- Status: aceito (2026-10-04)

## Contexto
O repositório é desenvolvido com três hosts de agentes de código: Claude Code, Codex e Devin. Cada host lê skills e instruções do seu próprio lugar, e os assets do workflow Kiro foram gerados por instalador upstream, um mirror por host:

- **Mirrors gerados por instalador.** As mesmas 17 skills `kiro-*` existem em `.claude/skills/`, `.agents/skills/` (Codex) e `.devin/skills/`, todas versionadas e entradas num único commit, sem sincronização manual desde então. Os arquivos de apoio (`rules/*.md` e `kiro-impl/templates/*.md`) são idênticos byte a byte nos três hosts. Contra as cópias de referência versionadas em `.kiro/settings/rules/`, só `ears-format.md` difere, pela substituição do placeholder de idioma feita na instalação. Os templates de `kiro-impl` não têm cópia de referência.
- **Sintaxe por host.** O conteúdo equivalente muda de forma: o Claude invoca skills com `/kiro-…` e declara `allowed-tools` (e, na maioria das skills, `argument-hint`) no frontmatter; o Codex invoca com `$kiro-…` e acrescenta `agents/openai.yaml` por skill; o Devin invoca com `/kiro-…` sem esses metadados. O Codex tem ainda um agente exclusivo, `.codex/agents/spec-reviewer.toml`, usado pelo `kiro-spec-batch`. Comparar texto byte a byte acusaria drift onde não há.
- **`AGENTS.md` compartilhado.** Codex e Devin leem o mesmo `AGENTS.md`, que hoje é a concatenação de dois blocos de instalador quase idênticos (Codex e Devin), sem nenhuma invariante do projeto. O Claude Code lê `CLAUDE.md`, que mistura as invariantes do Forge com as instruções Kiro.
- **Comandos legados.** `.claude/commands/kiro/` tem 11 comandos de uma geração antiga dos mesmos fluxos, só no Claude, cada um com skill equivalente (`spec-impl` corresponde a `kiro-impl`). Eles não usam os review gates das skills e duplicam o contexto listado na sessão.
- **Steering e specs locais.** `.kiro/specs/` e `.kiro/steering/` ficam fora do git por decisão do mantenedor; `.kiro/steering/` tem só `roadmap.md`, e os arquivos padrão `product.md`, `tech.md` e `structure.md` não existem. Também ficam locais `.claude/agents/` e `.agents/skills/source-command-*`. `.kiro/settings/` (regras e templates) é versionado.
- **Sem hooks.** Não há `.claude/settings.json` nem hook de desenvolvimento versionado; as verificações rodam no CI (`.github/workflows/`).

Nada disso toca o runtime: nenhum módulo de `src/theforge/` lê esses diretórios, e o wheel publicado contém só `src/theforge` (`[tool.hatch.build.targets.wheel]`).

## Alternativas
- **(A) Mirrors mantidos à mão, com auditoria e paridade testada.** Os três mirrors continuam como estão; uma ferramenta stdlib de manutenção (`scripts/agentic/audit_assets.py`, com configuração declarativa `scripts/agentic/agentic.toml`) compara as skills equivalentes por perfil semântico, os arquivos de apoio entre hosts e com `.kiro/settings/`, e um teste offline falha em drift não declarado. Custo de migração: nenhum. Custo recorrente: editar os três hosts na mesma mudança.
- **(B) Reinstalar a partir do instalador upstream com versão fixada, mais a auditoria.** Atualizar é reexecutar o instalador numa versão registrada. Custo de migração baixo, mas a reinstalação reescreve os mirrors e reconcatena os blocos do `AGENTS.md`, apagando o bloco de invariantes e as instruções curtas; toda reinstalação exige reaplicá-los e rodar a auditoria. Personalização local continua sendo à mão.
- **(C) Fonte canônica no repositório, renderizada por script stdlib.** `.kiro/settings/` é estendido com o corpo neutro de cada skill e um script stdlib renderiza os três hosts (prefixo de invocação, frontmatter, metadados por host). O drift é eliminado na origem. Custo de migração: extrair 17 corpos neutros dos 51 `SKILL.md`, escrever e testar o renderizador, verificar que a saída reproduz os mirrors atuais e passar a tratar os mirrors como gerados; conflita com reinstalações do instalador upstream, que deixam de ser o caminho de atualização.
- **(D) Plugin do Claude Code.** Empacotar skills, comandos, agentes e hooks como plugin do Claude. Serve só ao Claude: Codex continua lendo `.agents/skills/` e `AGENTS.md`, e Devin continua lendo `.devin/skills/` e `AGENTS.md`, então os mirrors continuam existindo. Como fonte, criaria um quarto lugar para sincronizar.

## Critério de decisão
Na ordem: independência do runtime (inegociável em qualquer alternativa), risco de divergência entre hosts, custo de manutenção observado (sincronizações manuais por ciclo), número de hosts e custo de migração. Hoje há três hosts, nenhuma sincronização manual registrada desde a instalação e arquivos de apoio idênticos: o risco de divergência é real, mas a auditoria o torna visível sem migrar nada.

## Decisão
- **Agora: (A).** Os mirrors continuam versionados e mantidos à mão, protegidos pela auditoria e pelo teste de paridade. Diferenças de sintaxe de host são toleradas pelo perfil semântico; divergências deliberadas ficam registradas como aceitas, com motivo, na configuração da auditoria.
- **Nenhuma migração nesta wave.** Nenhum asset é movido, gerado nem empacotado como plugin. Os comandos legados `.claude/commands/kiro/` são removidos por serem duplicatas cobertas pelas skills, não por migração.
- **Caminho recomendado: (C), com gatilho objetivo.** Migrar para a fonte canônica renderizada quando ocorrer qualquer um destes: (1) um quarto host com diretório de skills próprio for suportado; (2) três ou mais sincronizações manuais de mirrors num mesmo ciclo, contadas no histórico git como commits que alteram a mesma skill em mais de um diretório de host, excluídas reinstalações do instalador. A migração vira uma spec própria, com custo revisto naquele momento.
- **(B) é procedimento, não estratégia.** Reinstalar o instalador continua permitido para atualizar os fluxos Kiro, sempre seguido de reaplicar as instruções curtas e o bloco de invariantes e de rodar a auditoria até ela passar.
- **(D) só como empacotamento adicional.** Um plugin do Claude pode ser gerado a partir da fonte canônica depois de (C), nunca como fonte dos assets.
- **Runtime independente em qualquer alternativa.** O pacote `theforge` nunca inclui, lê nem requer os assets agentic; a ferramenta de auditoria fica em `scripts/`, fora do wheel, e não adiciona dependência de runtime ([ADR 0003](0003-python-stdlib-only.md)).
- **Assets locais continuam locais.** `.kiro/specs/`, `.kiro/steering/` (incluindo `roadmap.md` e os eventuais `product.md`, `tech.md` e `structure.md`), `.claude/agents/` e scaffolds de terceiros como `.agents/skills/source-command-*` ficam fora do git e nunca são obrigatórios para o repositório versionado. As skills funcionam sem steering; as regras persistentes do projeto vivem em `CLAUDE.md`, `AGENTS.md` e `docs/`. Nenhuma verificação, documento versionado ou instrução de host depende deles, e a auditoria lê só arquivos rastreados pelo git.

## Política de hooks
Esta wave não adiciona hooks. Se hooks de desenvolvimento forem adicionados (por exemplo, hooks de edição de um host de agente ou pre-commit):
- rodam só checagens focadas e determinísticas sobre os arquivos alterados: `ruff check` nos arquivos tocados, os testes relevantes à mudança, a paridade de schemas quando `src/theforge/contracts/` muda e a auditoria agentic quando assets agentic ou instruções de host mudam;
- nunca rodam a suíte completa a cada edição; a suíte completa e o gate `slow` continuam no CI e na validação explícita;
- nunca acessam a rede, nem dependem de providers reais, credenciais ou assets locais não versionados;
- não substituem o CI: um hook ausente ou desativado não muda o resultado do gate.

## Consequências
- O drift entre hosts passa a ser detectado por teste offline, com o mesmo resultado em Linux e Windows, sem custo de migração.
- **Limitação da paridade por perfil.** O perfil semântico compara nome, caminhos de repositório referenciados, skills referenciadas, fases de `spec.json` e arquivos de apoio. Prosa divergente que não muda nenhum desses elementos (por exemplo, uma instrução reescrita só num host) passa sem achado. É o custo de tolerar a sintaxe por host; (C) elimina essa lacuna na origem.
- Editar uma skill exige mudar os três hosts na mesma mudança; reinstalar o instalador exige reaplicar as instruções curtas e rodar a auditoria. O procedimento está em [docs/agentic.md](../agentic.md).
- A decisão é revisitada quando o gatilho disparar ou no início do próximo ciclo, com o histórico de sincronizações como evidência.

## Reavaliação (2026-10-05, ciclo 3 wave L)

- **Evidência de sincronizações:** `git log -- .claude/skills .agents/skills .devin/skills` mostra dois commits desde a instalação — `0955ba4` (a instalação upstream) e `1d01b49` (remoção dos comandos legados `.claude/commands/kiro/`, um host só). Nenhum commit alterou a mesma skill em mais de um diretório de host: sincronizações manuais contadas = **0** (< 3).
- **Número de hosts:** três (Claude Code, Codex, Devin); nenhum quarto host com diretório próprio foi adicionado.
- **Auditoria no momento da revisão:** `python scripts/agentic/audit_assets.py` sai com 0 achados de falha.
- **Decisão mantida: (A).** O gatilho objetivo não disparou; (C) continua o caminho recomendado quando disparar, e esta seção é atualizada a cada revisão.
