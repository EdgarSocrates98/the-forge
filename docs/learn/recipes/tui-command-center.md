# Receita — usar o Command Center (TUI)

**O quê:** `forge` sem argumentos num terminal interativo abre o Command
Center — dashboard com especialistas, task runner, hosts, graph studio,
install wizard, health e tasks recentes.
**Por que:** operação diária é vigilância + ação pontual; o TUI mostra o
estado real (não um logo) e executa os mesmos caminhos do CLI.
**Quando:** sessão interativa de operação — ver quem está instalado,
delegar uma task, abrir o host, conferir saúde.
**Quando não:** em pipe/CI (recusa `non-interactive` honesta) ou quando
você já sabe o verbo exato — o CLI direto é mais rápido.

## Problema

"Quero um painel único: quais forjas estão ativas, delegar uma task,
abrir meu host — sem decorar verbos."

## Pré-requisitos

Terminal com TTY; sem TTY o home recusa explicitamente
(`home requires a TTY`) — nunca degrada em silêncio.

## Passo a passo

```bash
theforge          # abre o Command Center
# menu: specialists | run a task | hosts | graph studio |
#       install wizard | health check | recent tasks | quit
```

- **specialists** — tabela real do catálogo (`theforge specialists`).
- **run a task** — o mesmo caminho de `forge task run` guiado.
- **hosts** — detecção por evidência (running/detected/not detected).
- **graph studio** — grafo federado no navegador (se habilitado no
  install; desabilitado diz explicitamente).
- **install wizard** — `forge install` plano→aprovação guiado.
- **health check** — `forge install doctor` renderizado.

## Saída esperada / interpretação

Cada item executa a função real do módulo (sem duplicar lógica): as
mesmas linhas de `forge status`, `forge specialists` etc. — nada é
placeholder.

## Verificação

Cada ação do menu corresponde 1:1 a um verbo/serviço real — saída do TUI
é idêntica à do CLI equivalente.

## Limitações

Terminal sem ANSI cai no kit inline (mesma semântica, menos chrome).
NO_COLOR respeitado. Hosts externos que pedem TTY própria
(`hosts launch`) ficam no CLI, não dentro do TUI.

## Erros comuns

| Sintoma | Causa | Ação |
|---|---|---|
| `home requires a TTY` | rodou `forge` num pipe | use `forge <verbo>` direto |
| "graph studio disabled" | componente desligado no install | reinstale com o componente |

## Uso por agentes

Agentes não usam o TUI — usam os mesmos verbos com `--json`. O TUI é a
superfície humana do mesmo núcleo.
