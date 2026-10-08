# ADR 0014 — Local dos adapters dos Forges reais

- Status: aceito (2026-10-04)

## Contexto
O Spark Forge (`sparkforge-aws`) e o API Forge (`apiforge`) não falam o Forge Protocol v1. Alguém precisa traduzir entre o protocolo (ADR 0001) e a superfície pública de cada um: `call_tool` e o catálogo de tools no Spark, a CLI e a matriz de capabilities no API. As restrições são:

- o core é stdlib-only e nunca faz `import sparkforge`/`apiforge`;
- o API Forge exige Python 3.12, e o core roda em Python ≥ 3.11;
- a Wave B não pode depender de mudança aceita nos repositórios irmãos;
- a conformance dos adapters precisa rodar no CI principal sem rede, sem AWS, sem credenciais e sem os irmãos.

Opções avaliadas:

- **A. Adapter dentro do pacote `theforge`** (`theforge.providers.sparkforge`/`apiforge`).
- **B. Entrada nativa em cada Forge** (`python -m sparkforge.forge_protocol`, `python -m apiforge.forge_protocol`), mantida pelo dono da superfície.
- **C. Distribuição separada mantida no repositório de The Forge** (`adapters/sparkforge`, `adapters/apiforge`), instalada no interpretador do especialista e registrada por `argv`.

## Critérios

| Critério | A. dentro do core | B. entrada nativa | C. distribuição separada |
|---|---|---|---|
| Acoplamento | o core passa a conhecer superfícies nativas; viola "nunca `import sparkforge`/`apiforge`" | mínimo: o dono traduz a própria superfície | a tradução fica do lado de The Forge, isolada em `adapters/` e fora do pacote `theforge` |
| Independência de release | o release do core acompanha cada mudança nativa | o protocolo muda junto com o release do Forge, e os dois lados precisam se coordenar | cada adapter tem a sua SemVer (`0.1.0`) e sai do ciclo do core e do especialista |
| Compatibilidade retroativa | quebra o core quando a superfície nativa muda | o Forge precisa manter o protocolo entre versões | janela explícita por adapter (`SUPPORTED_SPECIALIST`); fora dela, health `degraded` |
| Ownership | o time do core mantém um conhecimento que não é dele | o dono da superfície | o time de The Forge, com snapshot, teste de drift e janela de versão para detectar quando a superfície muda |
| Instalação | um pacote só, mas exige o especialista no interpretador do core (o API precisa de 3.12) | `pip install` do Forge já traz a entrada | um `pip install` a mais no interpretador do especialista; o core continua sem dependência de runtime |
| Segurança | o código do especialista roda no processo do core, com o ambiente do core | isolamento por processo (ADR 0001) | isolamento por processo (ADR 0001); ambiente filtrado pelo core, sem credenciais; estado nativo contido no cwd do run (ver abaixo) |
| Testes | exige os especialistas no ambiente de teste do core | não dá para testar no CI de The Forge sem os irmãos | conformance offline no CI principal via `--replay`; integração real em `real-providers.yml` |
| Version skew | não há janela: qualquer mudança nativa quebra o core | some do lado de The Forge e passa a ser problema do dono | janela por adapter, snapshot gravado da superfície nativa e drift verificado contra o Forge real |

## Decisão
- **C.** Duas distribuições stdlib-only, `theforge-sparkforge-adapter` e `theforge-apiforge-adapter`, em `adapters/sparkforge` e `adapters/apiforge`. Cada uma tem SemVer própria, `requires-python >=3.10` (piso do Spark Forge) e nenhuma dependência declarada: é instalada no interpretador onde o especialista já está. Nenhuma importa `theforge`, e o pacote `theforge` não importa nenhuma delas.
- O core vê só o `argv` registrado no `providers.toml` do usuário (`["<python do especialista>", "-m", "theforge_sparkforge"]`, idem `theforge_apiforge`) e os envelopes JSON.
- O envelope e a mecânica comum (`serve`, `stage_context`, `finalize`, `cleanup_workdir`, `run_native`) ficam em `_shell.py`, copiado byte a byte em todos os adapters. Um teste garante que as cópias são idênticas.
- `describe` deriva o manifest de uma tabela positiva de capabilities (`catalog.py`) cruzada com um snapshot gravado da superfície nativa (`native_catalog.json`, `native_matrix.json`). Só capabilities read-only e offline são declaradas; o resto vai para `limitations` com o motivo.
- O especialista roda sempre num processo filho com cwd no diretório do execute. No Spark, isso é uma errata do design, que previa chamada em processo: `python -m theforge_sparkforge.native_call` roda no mesmo interpretador. O motivo é que o ledger nativo (`.sparkforge/traces.db`) é gravado no `atexit` e recriaria arquivos depois da limpeza. O processo filho também fecha as conexões SQLite antes da limpeza e fica sob o timeout nativo. O custo é de 3–5 s por execute. No API, a CLI pública roda no mesmo interpretador. O cwd é o do execute, ou a raiz do workspace copiado quando o arquivo de entrada cita outros caminhos relativos (`change-control run`).

## Segurança e contenção
- O especialista lê só cópias conferidas do `ContextPack`. Cada arquivo é copiado para `<cwd>/stage/`, e o sha256 é conferido com o do pack. Arquivo fora da raiz, divergente ou com intervalo de linhas não é copiado e vira limitação.
- Em execute, o cwd é `.forge/runs/<id>/work/`. Estado e caches nativos (`.sparkforge/`, `traces.db`, `.apiforge/`, cache de caso) caem ali, nunca no workspace do usuário.
- **Exceção à invariante de redação.** `.forge/runs/<id>/work/` guarda dados escritos pelo provider, **não redigidos** por `security.redact`, e fica fora da invariante "tudo que o core persiste passa por `security.redact`". O core não conhece o formato desses arquivos e não os reescreve. O que fica ali (a saída nativa completa do spill, `native/full-output.json`, e os arquivos de caso do API Forge) pode conter trechos do código analisado. O diretório tem a mesma sensibilidade do workspace e não deve ser publicado.
- **Redução aos artifacts declarados.** Em todo desfecho de execute (`ok`, `partial`, `refused`, `error` e timeout), o adapter chama `cleanup_workdir` depois de montar a resposta. Ele apaga `stage/` e tudo o que não é path de `artifacts[]`, e mantém só os artifacts declarados, cujo sha256 já está no resultado. Uma remoção que falha vira a limitação `workdir cleanup incomplete: <path>`, nunca erro.
- Credenciais nunca chegam ao ambiente do adapter: o core filtra o ambiente, e as variáveis `THEFORGE_REAL_*` são lidas só pelo harness de teste. As únicas mudanças de ambiente feitas pelo adapter são `APIFORGE_CACHE=off` no API Forge e `PYTHONIOENCODING=utf-8` no processo filho do Spark; nomes com cara de credencial nunca passam ao processo nativo.
- Health não usa rede nem credenciais. O Spark nunca chama `doctor`, que sonda a cadeia de credenciais AWS. O API também não roda o `apiforge doctor` (errata de 2026-10-04): confere só Python 3.12, importabilidade e versão de `apiforge` e a existência de `apiforge.cli` (`find_spec`, sem importar), porque o import da CLI leva de 3 a 17 s, acima do orçamento de 10 s do core. Dependência quebrada da CLI aparece no `execute`, não no health.

## Gatilho de migração para entrada nativa (B)
Migrar um Forge para B quando as duas condições valerem:

1. o dono do repositório irmão aceitar manter uma entrada Forge Protocol v1 (`python -m <forge>.forge_protocol` ou equivalente) e publicar um release com ela;
2. essa entrada passar na conformance existente (`tests/test_conformance.py`) e na integração `real_provider` contra o mesmo workspace de exemplo, com manifest equivalente ao do adapter: mesmas capabilities, ações e limitações.

O protocolo não muda; muda só o `argv` registrado. O adapter correspondente vira depreciado e sai depois de uma janela de suporte da matriz de compatibilidade (`docs/versioning.md`).

## Alternativas rejeitadas
- **A:** viola a invariante de não importar especialistas, obriga o API Forge (3.12) a dividir o interpretador com o core e amarra o release do core às superfícies nativas.
- **B agora:** depende de aceitação e release externos e não é testável no CI de The Forge sem os irmãos. Fica como alvo, com o gatilho acima.

## Consequências
- The Forge carrega o custo de acompanhar as superfícies nativas. As mitigações são o snapshot gravado, o teste de drift contra o Forge real (workflow `real-providers.yml`), a janela de versão por adapter e a matriz de compatibilidade testada.
- Instalar um Forge real significa instalar dois pacotes no interpretador do especialista. O guia é [docs/real-providers.md](../real-providers.md).
- Depurar uma falha nativa exige reexecutar, porque o estado nativo é apagado. O resultado e o receipt já trazem o erro estruturado.
- O Spark paga 3–5 s de processo filho por execute.
