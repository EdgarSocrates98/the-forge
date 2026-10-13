# Forge Design System — baseline FASE 0

Linguagem de UX compartilhada das sete Forjas. Não é um framework novo:
é a **consolidação das convenções já provadas** nos projetos (install
receipts, DocMeta, refusal codes, TUI kit vendored), para que uma pessoa
que aprendeu uma Forja reconheça todas as outras.

Princípio da recomendação §Primeira: padroniza-se a **experiência e o
resultado**, não a implementação — cada host integra pelo melhor
mecanismo realmente suportado.

## 1. Voz e idioma

- Documentação de usuário: **português (Brasil)**; termos técnicos
  consagrados em inglês quando não há tradução honesta (handshake,
  provider, skill, finding).
- Código, IDs de regra, contratos e schemas: inglês.
- Tom: direto, operacional. Frase boa diz o que fazer; frase ruim admira
  o sistema. Proibido marketing no lugar de instrução.
- Estado honesto: `unverified`, `degraded`, `blocked`, `not_applicable`
  aparecem como estados reais na UI — nunca escondidos, nunca inflados.

## 2. Nomes e superfícies

| Conceito | Convenção |
|---|---|
| Comando canônico | sempre o nome completo (`theforge`, `apiforge`, `sparkforge-aws`…); alias (`forge`) nunca em exemplos de docs |
| Recusa | código `XX-YYY-NNN` do domínio (`AF-*`, `PF-*`, `SF-*`, `TF-*`, `FORGE-*`) + campo rejeitado + `unlock` |
| Estado de verificação | `verified`/`unverified`/`degraded`/`failed` — enums dos contratos `contracts/experience/` |
| Superfícies | `cli`, `tui`, `mcp`, `graph`, `knowledge` — mesmas palavras em todos os repos |
| Hosts | `devin`, `claude`, `codex`, `copilot` — sempre minúsculos em dados |

## 3. Estrutura de saída (CLI e agentes)

Toda saída de operação responde, na ordem que couber:

1. **Outcome** — o que aconteceu (estado, não adjetivo).
2. **Evidência** — `fact_id`/`rule_id`/hash/comando; sem evidência o
   outcome desce para `unverified`.
3. **Limitações** — o que a saída NÃO cobre.
4. **Next** — próximo passo acionável ou `unlock` quando bloqueado.

Recusas nunca são só mensagem: preservam código, campo e desbloqueio.

## 4. TUI — convenções do kit

O kit TUI vendored (`ui/` nos 7 repos) já é o design system visual:

- Home com **entradas reais** (verbo + DocMeta); nenhum botão sem ação.
- Non-TTY → fallback não-interativo explícito (menu inline ou
  `NonInteractive`), nunca crash nem spinner infinito.
- Estados de carregamento nomeados; operação longa mostra progresso real
  ou declara `running` — nunca finge conclusão.
- Drift de paridade entre os kits é bug (a suíte compara bytes com o
  canônico).

## 5. Agentes e skills — experiência padronizada

- **Agentes**: catálogo didático (`forge/AgentCatalog/v1`): purpose,
  when_to_use, **when_not_to_use**, expected_output, limitations.
- **Skills**: ativação declarada (`slash`, `description-match`,
  `agent-dispatch`…); o usuário nunca precisa adivinhar como chamar.
- **Roteamento**: intenção ambígua → `ambiguous` + candidatos; nunca
  execução por chute.
- **Subagentes por host**: cada host usa seu mecanismo nativo
  (`--agents`/plugins no Claude, `agents` no Codex, `run_subagent` no
  Devin). A experiência alvo é a mesma; o caminho não precisa ser.

## 6. Instalação — linguagem única

- Escopos: `project` → `workspace` → `user` (escopo maior nunca é
  presumido).
- Perfis: `economy` / `balanced` / `full` — nenhum reduz segurança.
- Ciclo: `status → doctor → plan → apply → verify` com receipt por
  operação; `unverified`/`uninitialized` carregam `unlock` com o comando
  exato.
- Seleção de host vazia é estado válido — reportada, nunca corrigida
  silenciosamente.

## 7. Documentação — camadas fixas

- `README.md`: o que a Forja faz, instalação mínima, **como usar agents e
  skills depois de instalada** (o valor), não lista de flags.
- `docs/learn/`: receitas progressivas (`why/when` por comando).
- `docs/reference/`: referência gerada; nunca editada à mão.
- `docs/errors.md` (ou equivalente): lista canônica de códigos — toda
  página que cita um código linka para ela.
- Estados de revisão por documento: `INVENTORIED →
  AUTOMATICALLY_CHECKED → TECHNICALLY_VERIFIED → SEMANTICALLY_REVIEWED →
  USER_JOURNEY_VALIDATED` (`forge/DocumentationReview/v1`). Inventário
  não é revisão.

## 8. Economia sem perda

- Resposta compacta é **projeção**, nunca fonte da verdade; artefatos
  completos persistem.
- Budgets nunca cobrem segurança, evidência ou relato de `unresolved`.
- Antes de gastar contexto: seleção (`knowledge select`), gate
  (`evidence gate`), capsule em vez de caso inteiro.
