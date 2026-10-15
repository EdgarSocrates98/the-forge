# Onboarding — jornada de primeiro uso

Uma jornada única de primeiro uso (§10.2). O objetivo: um desenvolvedor
externo instala, executa uma tarefa real e compreende o resultado — sem
conhecer dezenas de comandos e sem instruções privadas.

```text
Discover
   |
   v
Install
   |
   v
Choose Forge
   |
   v
Configure Host
   |
   v
Validate Environment
   |
   v
Run First Task
   |
   v
See Evidence
   |
   v
Explore Advanced Features
```

## O mínimo que você precisa digitar

```bash
cd seu/projeto
theforge setup        # jornada única: escopo, hosts, perfil, plano, aprovação
theforge doctor       # valida o ambiente instalado
theforge task "..."   # primeira tarefa real (roteada a um especialista)
theforge status       # onde está tudo
```

`theforge setup` apresenta numa única passada: escopo (`project`/`workspace`/
`user`), hosts (Devin, Claude, Codex, Copilot — ou nenhum), perfil
(`minimal`/`recommended`/`full`), perfil de execução do roteador
(`economy`/`balanced`/`deep`), componentes, o plano real das Forjas
registradas, uma aprovação única, aplicação e verificação. Nada é escrito
antes da aprovação — veja `docs/installation/family-onboarding.md`.

## Os 8 estágios, mapeados a comandos reais

| Estágio | O que acontece | Comando |
|---|---|---|
| **Discover** | Você descobre o que cada Forja faz — o catálogo vem dos manifests, não de marketing | `theforge specialists list`, `theforge capabilities` |
| **Install** | Uma jornada única instala o núcleo + especialistas registradas | `theforge setup` (ou `theforge install auto`) |
| **Choose Forge** | Você declara intenção; o roteador escolhe deterministicamente — ambiguidade vira `ambiguous`, nunca um chute | `theforge ask "sua intenção"` |
| **Configure Host** | Skills/agents/MCP são ativados nos hosts que você escolheu | etapa de hosts do `theforge setup`; `theforge hosts` |
| **Validate Environment** | O doctor confere SO, Python, git, workspace e providers | `theforge doctor` |
| **Run First Task** | Primeira tarefa real, executada pelo especialista via argv real | `theforge task "descreva a tarefa"` |
| **See Evidence** | Cada execução grava receipts verificáveis — sucesso só com `ExecutionResult` válido | `theforge explain`, `theforge replay`, `theforge status` |
| **Explore Advanced Features** | Benchmarks, Portal, grafo de capacidades, multi-forge | `theforge lab`, `theforge portal`, `theforge graph` |

## Guias por perfil

Escolha o seu ponto de partida em `docs/onboarding/getting-started/` —
11 perfis, cada um com pré-requisitos, instalação, configuração, primeiro
comando, resultado esperado, explicação, troubleshooting e próximos passos.

## Golden Paths

Caminhos completos ponta-a-ponta em `docs/onboarding/golden-paths/`:
Spark AWS ("meu job Glue está lento"), API ("preciso revisar e evoluir uma
API"), Platform ("preciso avaliar a segurança da infra") e Multi-Forge
("minha aplicação tem API + infra + pipelines").

## Regras honestas

- Nenhum benchmark é publicado sem medição real — `docs/programs/ecosystem-2026/benchmarks/`.
- `not_available`/`skipped` nunca viram `pass`.
- Se um especialista não estiver instalado, o roteador diz `not installed` —
  nunca simula a capacidade.
