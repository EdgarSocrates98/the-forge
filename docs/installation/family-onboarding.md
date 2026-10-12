# Onboarding da família de Forjas

O comando recomendado para quem quer usar o The Forge como roteador é:

```bash
cd /caminho/do/projeto
theforge setup
```

O wizard apresenta, em uma única jornada:

1. escopo: `project`, `workspace` ou `user`;
2. hosts: Devin, Claude, Codex e Copilot, incluindo a opção explícita de não configurar hosts;
3. perfil de instalação: `minimal`, `recommended` ou `full`;
4. perfil de execução do roteador: `economy`, `balanced` ou `deep`;
5. componentes: skills, agents, MCP, TUI e Graph Studio;
6. plano real de todas as Forjas registradas;
7. uma aprovação única;
8. aplicação, saúde e próximos passos.

Nada é escrito antes da aprovação. O plano usa os instaladores reais de cada
Forja, preservando seus ledgers, rollback e verificações próprias.

## Perfis

`minimal` instala o núcleo e MCP. Skills, agents, conhecimento e evals ficam
disponíveis pelos pacotes/registro e são carregados sob demanda pelo roteador;
nenhuma cópia indiscriminada é feita no projeto.

`recommended` habilita skills, agents, MCP, TUI e Graph Studio. É o ponto de
partida para a maioria dos projetos.

`full` mantém todos os componentes compatíveis selecionados. O tamanho do
contexto continua sob controle do perfil de execução e da descoberta
progressiva; full não significa enviar todo o catálogo em toda tarefa.

## Automação e revisão

Para CI ou scripts, use o mesmo contrato sem prompts:

```bash
theforge setup --scope project --host all --profile recommended --dry-run
theforge setup --scope project --host all --profile recommended --yes
```

`--dry-run` nunca cria ledger, estado ou arquivo de host. `--yes` só deve ser
usado quando o plano já foi revisado pelo operador.

O equivalente avançado permanece disponível:

```bash
theforge install auto --scope workspace --member apps/api
```

As escolhas de host, perfil e componentes são propagadas para cada CLI
registrada. Se uma Forja não estiver registrada em `~/.forge/installations`, o
The Forge informa o bloqueio em vez de simular uma instalação.

## Depois da instalação

```bash
theforge specialists status
theforge doctor
theforge portal
```

O Portal mostra a família, o estado de cada especialista, MCP, checkouts,
grafo e o mesmo fluxo plan → revisão → apply.
