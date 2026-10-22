# ADR 0061 — `.forge/context/`: registry de contexto por workspace + contrato `forge/context/v1`

- Status: aceito (2026-10-22) — install-2.0 ciclo 2 (spec lf-0035), evidência:
  audit `docs/audits/FORGE_CONTEXT_BASELINE.md` §5 P1-3/P1-4

## Contexto

O audit do install-2.0 ciclo 1 (lf-0034) mediu o que uma instalação por
wheel entrega hoje: skills + marcadores chegam ao alvo, mas **nada no
workspace diz ao host o que a forge é, o que ela sabe ou onde recuperar
conhecimento** (P1-3/P1-4 do baseline). `forge_knowledge` fica bundled no
pacote sem nenhum handle no alvo; `agentic/agents` nem chegava no wheel
(P0-1). Registries existentes não cobrem o caso: `~/.forge/installations/`
é nível *conta* (escrito pelo bootstrap, diz "a forge existe"), e
`.forge/install/` é o ledger de *arquivos gerenciados* (diz "o que foi
copiado"). Falta a camada *workspace*: "quais forjas operam aqui, com
quais domínios, interfaces e estado".

Sob Feature Freeze (`docs/feature-freeze.md`) subsistema novo exige ADR
com evidência de dogfooding. A evidência é o próprio baseline: matriz de
recursos mostrando 6 linhas de capability instaladas sem handle de
descoberta, e a execução real fora do checkout provando `agents list`
vazio e `--components agents` gravando 0 arquivos.

## Decisão

1. **Contrato `forge/context/v1`** (manifesto de capacidades por forge) e
   **`forge/context-registry/v1`** (documento de workspace), publicados em
   `docs/portable-installation/schemas/` — a casa canônica dos schemas
   `forge/*` desde ADR-0058. O manifesto carrega: identificador estável,
   nome, versões de pacote e de protocolo, domínios, capabilities com
   status/discovery/count, listas de skills/agents/coordinators/
   knowledge_providers/eval_suites/protocols/rule_areas, comandos de
   descoberta, interfaces de recuperação (cli/mcp/python/executable),
   hosts e modos de instalação suportados, localização de recursos,
   requisitos de runtime, restrições de segurança, perfil instalado,
   disponibilidade offline, estado degradado com razões obrigatórias,
   health checks e comprovação de integridade (sha256 das fontes de
   metadados).
2. **`.forge/context/` no alvo resolvido**: `registry.json` (doc
   compartilhado, regenerado deterministicamente das entradas por forge),
   `capabilities/<forge-id>.json` (um por forge) e `ROUTING.md`
   (roteamento humano-legível: domínio→forge, escopo, ambiguidade
   explícita). Camada nova — não toca o registry de conta nem o ledger.
3. **Motor vendored `_forgecontext.py`**: fonte canônica única em
   `scripts/installkit/forge_context.py`, copiada byte-idêntica com
   `_SOURCE_SHA256` para cada pacote (`vendor.py`), mesmo padrão de
   `_installkit.py`/`_graphview.py`. stdlib-only (ADR-0003), self-contained
   (não importa o installkit — cada forge pode vendorar sozinha). Escrita
   atômica tmp+rename, lock O_EXCL com reclaim de lock morto, journal
   redo: uma interrupção entre journal e apply converge na próxima op ou
   em `repair_context`. Sem The Forge, sem segredos.
4. **Ownership (spec §4.3)**: `registry.json`/`ROUTING.md` são `shared`;
   `capabilities/<fid>.json` é `fully-managed` por `<fid>`. A API exige
   `owner=`: uma forge só registra/desregistra a si mesma; manifesto
   estrangeiro no nosso path recusa `FORGE-CONTEXT-OWNERSHIP`; arquivo
   corrompido mas nosso vai para quarentena `.corrupt-<ts>` (nunca apagado
   em silêncio). Vocabulário completo — fully-managed / shared /
   managed-block / user / preexisting / foreign-installer — fica
   declarado no campo `ownership` do registry.
5. **Idempotente byte a byte**: re-registrar manifesto inalterado (só
   `recorded_at` novo) executa **zero writes** — prova testável de
   idempotência, não só semântica.
6. **Compatibilidade §4.4**: nenhum manifesto estável é substituído.
   `forge.json`/`forge.agentic.json`/`manifest.json` continuam sendo as
   fontes; `build_manifest()` os consome como metadados e atesta seus
   hashes em `integrity.files`. Adapters sobre `forge/*` v1 existente,
   nunca migração.

## Consequências

- Cada `<cli> install` passa a escrever também `.forge/context/` — os
  quatro especialistas recebem a cópia vendored + wiring mínimo no mesmo
  ciclo; templates completos de entry points ficam para lf-0036.
- `uninstall` remove somente o próprio manifesto + a própria entrada —
  recusa nomeada se outra forge for o alvo.
- O P0-1 do baseline (`agentic/agents` fora do wheel) é corrigido neste
  ciclo como bugfix: force-include + fallback bundled em `agents.py`
  (padrão `knowledge.py`) + gate de wheel — "os recursos que o contrato
  descreve precisam viajar no pacote".
- `ROUTING.md` é gerado, nunca editado à mão; ambiguidade de domínio é
  renderizada como tabela explícita, não escondida.
