# ADR 0015 — Inteligência de contexto: tiers, perfis, fingerprints e TOCTOU

- Status: aceito (2026-10-04)

## Contexto
Até a Wave A, o Context Broker selecionava só arquivos casados pelos globs da capability, lia todo arquivo selecionado para calcular o hash e entregava sempre arquivos inteiros (ADR 0007). Os perfis só variavam bytes e tempo, em tabelas separadas. Não havia como o provider pedir mais contexto, nem como detectar que um arquivo mudou entre o hash e a leitura (TOCTOU), e tokens eram reportados sem distinção do que foi medido.

## Decisão
- **Por referência, por tiers.** O ContextPack continua sem conteúdo (ADR 0007). Tiers: `metadata` (resumo do workspace, 0 bytes, sempre presente), `reference` (arquivo inteiro), `excerpt` (intervalo de linhas 1-based inclusivo, hash e bytes do intervalo) e `requested` (acrescentado por pedido). Tiers efetivos = tiers do perfil ∩ declaração da capability (`context.excerpts`, `context.requests`); sem declaração, o provider recebe o mesmo que na v1.
- **Seleção determinística por sinais genéricos**: `intent_lines`, `intent_path`, `target:<alvo>`, `glob:<glob>`, `git:changed` e `dependency_manifest`, com prioridade fixa e desempate pelo caminho. Sem LLM, embeddings, rede ou regra de domínio; arquivos sem sinal só entram no agregado `unmatched_files`. Cada item e cada exclusão registram seus sinais e um motivo de um conjunto fechado.
- **Perfis numa tabela única** (`profiles.py`): budget, `max_files`, tiers, rodadas de negociação (no máximo 2), `max_providers` (só registrado), fallback de health, nível de verificação e timeout de `execute`. `economy` deixa de fazer fallback de health.
- **Pedido de contexto limitado**: o provider pode pedir itens adicionais em `ExecutionResult.context_request` só se a capability declara `context.requests`, até as rodadas do perfil e com 1 a 64 itens; cada item passa pelas regras da seleção inicial e pelo budget restante. Falhas têm códigos próprios (`FORGE-CONTEXT-REQUEST-UNSUPPORTED`, `-LIMIT`, `-INVALID`). Cada pack estendido é um artefato (`context-r1`, `context-r2`) com hash no receipt.
- **Cache de fingerprints fora do projeto**: `<cache do usuário>/context/<digest12>.json` (mesmo modelo do ADR 0009). Um sha256 só é reutilizado quando `size`, `mtime_ns`, `ctime_ns`, `ino`, `dev` e o caminho resolvido batem e a entrada foi registrada mais de 2 s depois do `mtime`; qualquer outra evidência de mudança força leitura. Releitura estrita, gravação atômica uma vez por run, entradas com caminho em formato de segredo descartadas antes da redação do documento, e cache desligado se o diretório cair dentro do workspace. Com ou sem cache, os hashes são idênticos.
- **TOCTOU**: `Evidence.hash` passa a ter semântica normativa (sha256 de exatamente o conteúdo entregue no caminho: arquivo inteiro ou intervalo do item; nulo em qualquer outro caso). O provider revalida e informa o hash, ou declara `context_revalidation` (`hash`, `core`, `none`); sem declaração, o run registra `undeclared`. O core reverifica conforme o nível do perfil (`minimal`: nada; `conditional`: itens de evidências `confirmed`/`observed`; `strong`: todos). Divergência rebaixa essas evidências para `unresolved` e o run termina `partial`, nunca `ok`.
- **Bytes medidos, tokens honestos**: `tier_bytes` por tier; `tokens` do pack é sempre `unknown`; os tokens do provider só são mantidos quando `measured` ou `estimated`.
- **Telemetria por run** (`RunTelemetry` v1, schema fechado), gravada em todo desfecho e ligada ao receipt por `telemetry_sha256`.
- **Medir antes de otimizar**: baseline registrado com origem antes do cache e budgets de regressão derivados dele ([performance.md](../performance.md)).

## Alternativas
- **Enviar conteúdo no ContextPack**: persistiria conteúdo do workspace nos runs e quebraria o ADR 0007.
- **Seleção semântica (embeddings/LLM)**: não determinística e fora do invariante "sem LLM no core".
- **Cache em `.forge/cache/`**: o repositório analisado poderia pré-popular hashes falsos (o mesmo problema que motivou o ADR 0009).
- **Reusar hash só por `mtime` e tamanho**: falha com relógio de baixa resolução e escrita dentro do mesmo tick (janela racy).
- **Confiar só no provider para TOCTOU**: a declaração não é verificável; por isso o core também reverifica, conforme o perfil.
- **Negociação ilimitada**: custo e tempo sem teto; ficou em 2 rodadas no máximo.

## Consequências
- Contratos só ganham campos opcionais dentro de `theforge/<Name>/v1`; providers v1 e runs antigos continuam válidos. O hash dos manifests muda uma vez (defaults novos) e o cache do registry é regenerado.
- O ContextPack passa a incluir arquivos citados, de alvo, alterados no git e de dependência, além dos casados por glob, e o run pode terminar `partial` por drift.
- `economy` com primário unhealthy agora é `provider_failure` mesmo havendo fallback compatível.
- Cada rodada de negociação tem o timeout inteiro do perfil: em `max`, até 3 × 600 s em `execute`.
- No Windows, `ctime` é horário de criação: evidência de mudança mais fraca que no POSIX (os demais campos e a janela racy continuam valendo).
- Fora do modelo, como no ADR 0009: usuário local com escrita no próprio home. A reverificação só cobre o que o nível do perfil manda checar (`economy` registra `context-not-reverified`).
- Mudança no local ou formato do cache exige revisar este ADR e `docs/security.md`; mudança na semântica de `Evidence.hash` exige revalidar os adapters que a preenchem.
