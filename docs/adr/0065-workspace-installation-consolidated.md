# ADR 0065 — Plano de instalação consolidado e inventário de posse cross-forge

- Status: aceito (2026-11-06)

## Contexto

ADR-0058 estabeleceu o ciclo de vida portátil (kit vendored, escopos,
registry `~/.forge/installations/`, `install auto` delegando ao CLI de cada
forge). A delegação resolvia a pergunta "quem instala", mas deixava três
lacunas de control plane:

1. **Sem plano antes de escrever.** `install auto` aplicava forge a forge;
   a primeira falha já tinha gravado arquivos. Nada consolidava o que a
   família faria *antes* de tocar o alvo.
2. **Sem posse cross-forge.** Duas forges planejando o mesmo asset
   (`.agents/skills/x/SKILL.md`) produziam *last-writer-wins* — a última a
   executar ganhava, em silêncio. O ledger protegia contra conteúdo
   estranho, não contra outra forge legítima disputando o mesmo path.
3. **Capacidade presumida.** O argv de delegação mandava a família padrão
   de flags (`--scope`, `--yes`, `--host`, …) para qualquer forge
   registrada, declarasse ela suporte ou não — o control plane fabricava
   uma superfície que o manifesto nunca declarou.

A spec `install-2.1` (cycle-16 wave-01 parte 2) fecha as três lacunas sem
criar runtime novo: o plano consolidado é uma extensão do contrato
`forge/*` existente.

## Decisão

1. **`forge/WorkspaceInstallation/v2`** (novo contrato em
   `src/theforge/contracts/workspace_installation.py`, schema em
   `schemas/WorkspaceInstallation.schema.json`): o documento consolidado —
   raiz, ordem, forges com superfície declarada + classificação + posse +
   verificação, `conflicts[]` com winner/loser e `members[]`. Persiste sob
   o bloco `installation` do `forge/WorkspaceInstall/v1` — extende, nunca
   substitui a semântica append-only de `projects[]`.

2. **Manifesto declara, o orquestrador consome.**
   `forge/InstallationManifest/v1` ganha campos opcionais
   `installation_kind` (`content`|`service`|`control-tool`), `install`
   (operations/flags/hosts/scopes/profiles/approval) e `depends_on`. O
   bootstrap propaga `forge.json` → registry manifest validando o kind.
   Sem `install` declarado vale a família padrão v1 — compatibilidade
   retroativa. Com `install.flags` declarado, uma flag de request fora da
   lista torna o request *unhonorable*: `E_UNSUPPORTED`, nunca ampliação
   silenciosa.

3. **Planejar tudo antes de escrever.** `install_auto` coleta o plano de
   CADA forge antes de qualquer apply — `kit.plan()` em-processo para
   the-forge, o receipt `--dry-run` do próprio filho para siblings. Sem
   evidência de plano a entrada diz `unsupported`/`unavailable`, nunca
   fabrica paths. A aprovação (`--yes` ou `--dry-run`) gateia até a coleta
   de plano.

4. **Ordem determinística honesta.** `depends_on` declarado → Kahn
   topológico; dependência não declarada → ordem estável
   (`control-tool → service → content`, depois `forge_id`) com nota
   honesta no documento. Ciclos quebrados são registrados, nunca
   ignorados em silêncio; deps com nomes desconhecidos são nota, não
   bloqueio.

5. **Conflito de path cross-forge com winner/loser.** Colisão em asset
   managed de arquivo inteiro (`skill`, `agent`, `knowledge`, `rules`,
   `evals`, `config`, `state`) é conflito declarado — `mcp` (chave
   namespaced em `.mcp.json`) e `marker` (bloco delimitado por forge)
   nunca conflitam. O winner é o incumbente cujos bytes planejados já
   estão no disco; senão, o primeiro na ordem de instalação. O loser
   recebe `exclude` (in-process) ou é detectado via receipt: escrever
   mesmo assim é `overwritten — plan violation` → FAIL nomeado, nunca
   last-writer-wins silencioso.

6. **Classificação fechada.** `new|updated|reused|preserved|conflict|
   unsupported-capability` por forge — o documento nunca inventa
   categorias; evidência indisponível vira `null` com detalhe honesto.

7. **Posse com proveniência.** `owned_paths` + `resources[]` (id
   qualificado `<forge>:<path>`, sha256, owner, policy) distinguem a fonte
   da evidência: `receipt` = o receipt aplicado provou; `plan` = posse
   projetada de um dry-run (nada gravado ainda). Fontes vazias ficam
   `null`, nunca presumidas.

8. **Aprovação default-Não.** `confirm` interativo e o wizard pedem `y`
   explícito para escrever — Enter vazio aborta (rc 130). Dry-run continua
   livre de aprovação.

9. **`theforge init` escreve o marcador.** `forge.workspace.yaml`
   (`forge_workspace: true`) torna o diretório reconhecível pela busca de
   workspace-root do installkit — `init` + `install --scope workspace`
   fecha o round-trip.

## Alternativas rejeitadas

1. Planos em série com apply imediato: mantinha last-writer-wins e sem
   visão consolidada — o motivo da onda.
2. Inventário derivado de um ledger global cross-forge: misturaria a
   autoridade de posse por forge; a inventory é *evidência* do que cada
   receipt provou, não um ledger segundo.
3. Inferir capacidades do CLI instalado (probe `--help`): frágil e
   não-determinístico — declaração no manifesto é a única superfície
   honesta.
4. Winner por prioridade global de forge (ex.: the-forge sempre vence):
   arbitrário; o incumbente-no-disco e a ordem de instalação são
   determinísticos e explicáveis.
5. Resolver conflitos com merge de conteúdo: fora do escopo — arquivos
   managed são owned por uma forge, o loser pula e o humano decide.

## Riscos e evidência de aceitação

| Risco | Mitigação | Evidência mínima |
|---|---|---|
| Sibling sem receipt de plano | entrada `unavailable`, classificação honesta | `test_unsupported_capability_classification` |
| Winner escreve depois do loser | ordem de instalação = ordem de apply; receipt do loser decide resolução | `test_cross_forge_path_conflict_plan_and_apply` |
| Loser rogue sobrescreve | `overwritten — plan violation` FAIL nomeado | `test_loser_overwriting_is_named_not_silent` |
| Posse de dry-run confundida com posse real | `ownership_source` `plan` vs `receipt` | `test_workspace_install_json_carries_installation` |
| Request flag não declarada | `E_UNSUPPORTED`, nunca ampliação | `test_delegated_cmd_honors_declared_flags` |
| Ciclo em `depends_on` | quebra determinística + nota | `test_install_order_cycle_broken_honestly` |
| Enter vazio aplica | default `False` em `confirm`/`approve_plan`/wizard | `test_approve_plan_defaults_to_no` |

## Consequências

- `schemas/WorkspaceInstallation.schema.json` novo; `WorkspaceInstall`
  ganha bloco `installation` opcional.
- `forge/InstallationManifest/v1` documenta os três campos novos;
  `forge.json` de the-forge declara `control-tool` + superfície completa
  como referência.
- `tests/test_workspace_installation.py` cobre contrato, ordem,
  conflitos, inventário, marker e default-Não.
- Sinais ganham eixos de classificação (`platform`/`service`/`language`/
  `artifact_type`) + `axes_index()` — indexação/discovery, NUNCA entrada
  de roteamento (invariante de routing intacto).
