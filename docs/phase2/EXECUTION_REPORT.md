# Phase 2 — Execution Report

Data: 2026-11-10. Este relatório centraliza a execução do programa de integração
Obsidian/Cycle 2.0–2.6. Evidência local usa fixtures e não autoriza inferência
de execução em cloud ou em vault de usuário.

| Gate | Estado | Evidência principal | Limitação |
|---|---|---|---|
| G0 baseline/arquitetura | PASS | `BASELINE.md`, `OWNERSHIP_MATRIX.md` | índices de código são best-effort |
| G1 correções P0/P1 | PASS | commits por Forge registrados no baseline; Product regression local 82,62%; The Forge `6ca5ffd` corrige os stubs de `jsonschema`, mypy em 313 arquivos sem erros e CI `42688316906` verde em pacote Linux/Windows e Python 3.11–3.14; Agent Bridge `42687526019`, API `42694647843`, Azure `42693963092`, Platform `42692546513` e AWS `42714263493` verdes; AWS fechou 15122 passed/20 skipped em Python 3.10–3.14, wheels, auditoria e claims; correções Python 3.10 em AWS/Azure/Platform e Path flavor no API; auditoria local de 15 repositórios/50 workflows/335 ações externas sem refs mutáveis | gates externos de publicação/OIDC e operação produtiva continuam fora desta prova |
| G2 contratos/schemas | PASS | `tests/test_schemas.py` e `tests/test_fuzz_contracts.py` verdes; `KnowledgeDocument/v1` agora valida `knowledge_state`; schemas Obsidian v1 | compatibilidade externa não foi exercitada |
| G3 segurança/autorização | PASS local | traversal, symlink/reparse, hardlink, classificação, raiz autorizada, prompt-safety e redaction nos quatro adapters; títulos, summaries e campos estruturados não carregam segredos nas projeções Obsidian | permissão real e vault multiusuário não executados |
| G4 formatos | PASS local | Markdown, frontmatter, links, embeds, Canvas estrutural e Bases em YAML oficial com serializer/validador de `forge_obsidian` | não é parser/runtime completo do aplicativo Obsidian; fórmulas e filtros não são executados pelo Product Forge |
| G5 integridade de sync | PASS local + CI | Product Forge `77dde99` — 291 passed, 1 skipped; `-m not benchmark`: 287 passed, 1 skipped, 3 deselected; `forge_obsidian` distribuível sem dependência do runtime Product Forge; wheel/sdist `forge-obsidian` construídos pelo fluxo wheel-from-sdist; plan/baseline/conflict/atomic/rollback/skip/lock, índice seguro de paths, importação governada de investigação e ciclo de conhecimento evidence-gated; fault injection para permission denied e disk full; ensaio Windows com ACL real negando escrita retornou `OBSIDIAN-PATH-REFUSED`/`sync_state=denied` sem criar nota; ensaio real em tmpfs de 256 KiB cobriu ENOSPC durante o lock e retornou `OBSIDIAN-LOCK-FAILED`/`sync_state=failed` sem nota, receipt ou temporário parcial; pipeline standalone OIDC preparada em `445b4f0` e protegida por teste estrutural em `1490ff3`; Ruff limpo e CI remoto `42729793620` verde | dispatch/publicação remota da pipeline PyPI, pin pelos adapters e disk-full em ambiente produtivo ainda não executados |
| G6 adapters | PASS fixture + smoke cloud | AWS, Azure, API e Platform no runner federado; commits publicados `02db7ec`, `1009366`, `7b690bd`, `4ada2b7`, `27dd3f4`, `58a6117` e `f15fd51`; cada adapter tem 2 testes de projeção cobrindo redaction de campos, `title` e `summary`; AWS fechou 15122 passed/20 skipped em Python 3.10–3.14 no CI anterior, com claims e integridade de artefatos; coletor AWS `parquet-footer` validado em S3 temporário e removido; API `42736176051`/`42736175647`, Platform `42738344886` e Azure `42737901068` verdes; no AWS `42737900885` do SHA antigo, Python 3.11–3.14, wheels e auditoria passaram, mas Python 3.10 foi cancelado no limite e o run terminou `cancelled`; novo run `42750089008` do SHA `4ada2b7` está `pending` com matriz 3.10–3.14 e timeout de 180 minutos | Glue/EMR/Athena/CloudWatch e cenários de produção não exercitados; CI completo verde do SHA AWS atual ainda é necessário para fechar a homologação remota final |
| G7 recuperação agêntica | PARTIAL | processo encerrado durante temporário e recuperação subsequente verificados; fault injection de disk full; ensaio Windows com ACL real negando escrita retornou `OBSIDIAN-PATH-REFUSED`/`sync_state=denied`, sem artefato parcial e com ACL restaurado; ensaio real em tmpfs cheio retornou `OBSIDIAN-LOCK-FAILED`/`sync_state=failed`, sem nota, receipt ou temporário parcial | disk-full em vault/host produtivo e ensaio operacional de recuperação ainda pendentes |
| G8 E2E federado | PASS fixture | `FEDERATED_E2E_EVIDENCE.md`; 4 notas produzidas pelos adapters, 4 contratos `ObsidianNoteRef` validados contra schema, round-trip, Atlas, Lens, Bridge e conflito manual | não é homologação cloud/vault de usuário; runner de fixtures é separado do endpoint de investigação |
| G9 Portal/UX | PASS local | 624 testes frontend em 57 arquivos + suíte browser completa `uv run pytest -q e2e/test_browser_homologation.py`; Nova investigação com evidências, plano assinado, execução federada, recibo e handoff explícito para índice Product Forge; conhecimento com conexão, descoberta body-free de paths, preview, import/export, conflitos, histórico, ciclo de revisão e deep link Obsidian; gate visual 8/8, axe/overflow/foco = 0; pacote instalado fora do checkout com CLI/TUI/status/start estático e HTTP 200 | gravação no Obsidian continua sendo sync revisado e explícito; produção/OIDC pendentes |
| G10 instalação/distribuição | PASS local | matriz Python 12/12 wheel→venv→CLI passou no Windows e Linux WSL2; matriz limpa do wheel The Forge project/workspace/user passou com apply/uninstall; Product Forge wheel/venv/Portal fake passou; `forge-cli` e Portal Node build/pack passaram; matriz TTY/TUI 14/14 e cancelamento 14/14 verdes; MCP handshake real The Forge PASS com 15 tools e exit code 0; Product Forge publica 17 tools, incluindo índice Obsidian read-only | OIDC e matriz remota global ainda pendentes |
| G11 performance/regressão | PARTIAL | receipt observável de scan/import/wikilinks/export/reindex/search, orçamento de contexto estimado, qualidade de citações fixture, gateway com provider controlado e pico Python/RSS em 100/1.000/10.000; suíte completa Product Forge `291 passed, 1 skipped`; importação de 10.000 notas e resolução `10.000/10.000` passaram | uso real de tokens de provider `NOT_RUN`; RSS é amostrado por API stdlib e picos sub-5 ms podem ser subestimados; wall-clock de filesystem recém-criado (16,90 s em uma amostra Windows) fica registrado para tendência, não como limite arbitrário |
| G12 release readiness | BLOCKED | The Forge e Product Forge têm CI remoto verde; base funcional integrada | aceite global ainda depende da matriz instalada de todas as Forjas e dos riscos operacionais descritos em `REMAINING_RISKS.md` |

## Comandos de referência

```powershell
cd E:\projetos\FORJAS\product-forge
uv run pytest -q -rs
# 268 passed, 1 skipped (installed-system lane opt-in)

cd E:\projetos\FORJAS\the-forge
uv run python scripts/phase2_federated_obsidian_e2e.py --repos-root E:\projetos\FORJAS
# fixture_only=true, notes_roundtripped=4, manual_conflict_detected=true
```

O teste ignorado na suíte padrão não foi contado como aprovado; a mesma lane de
composição instalada foi executada separadamente com
`PRODUCT_FORGE_SYSTEM_HARNESS=1` e passou no Windows (`1 passed`).

O detalhamento requisito-a-requisito, com commit, comando, ambiente, resultado,
limitação e estado de cada G0–G12, está no
[`QUALITY_GATE_LEDGER.md`](QUALITY_GATE_LEDGER.md).

## Revalidação incremental — 2026-11-09

Após a execução inicial do relatório, as correções foram revalidadas nas
árvores atuais:

- Platform Forge: `uv run pytest -q --disable-warnings` terminou sem falhas;
- Spark Forge Azure: `3190 passed, 9 skipped`; freshness/knowledge focado adicional:
  `54 passed`;
- API Forge: a suíte completa terminou com `2028 passed, 4 skipped`; a correção
  `74bbbab` endureceu temporários únicos e retry de publicação atômica no
  Windows; gateway, refs, trust e projeção Obsidian permaneceram verdes;
- Spark Forge AWS: a suíte completa terminou com `15128 passed, 14 skipped`;
  claims `0 divergências`; status, evals, sincronização de
  skills e bundle offline passaram; `sparkforge-aws collect parquet-footer`
  foi homologado contra S3 real com perfil AWS CLI Login, região explícita,
  `status=ok`, 1 arquivo, 2 linhas e 2 colunas; o bucket/objeto temporários
  foram excluídos e a consulta posterior retornou `NoSuchBucket`;
- Code Atlas: `1667 passed, 21 skipped`; Agent Bridge: `130 passed`; Forge Lens
  terminou sem falhas na suíte completa; os skips permanecem classificados por
  capacidade de ambiente (symlink/LSP/POSIX) e não foram tratados como passes;
- E2E federado: `notes_exported=4`, `notes_roundtripped=4`,
  `manual_conflict_detected=true`, `cloud_access=false`.
- Portal Python: `python -m pytest -q tests` terminou com `200 passed, 15 skipped`.
  Portal Angular: `npm test -- --no-watch --no-progress` terminou com `57`
  arquivos e `624` testes verdes; `npm run build` gerou o bundle de produção.
  A suíte browser real completa passou (`10 passed` em 201,63 s): o bundle atual
  foi servido pelo adaptador real do The Forge e percorreu federação, Graph
  Studio, catálogos, recibo MCP, retorno ao grafo, instalação, estados
  degradados e investigação.
- O endpoint real `/mcp/verify` deixou de bloquear o Portal quando um launcher
  Windows mantém stderr aberto: `02c3501` drena stderr sem leitura bloqueante e
  encerra a árvore exata do processo. A regressão do installkit e a
  homologação real do The Forge passaram; a operação ainda reporta por servidor
  `PASS`, `FAIL`, `BLOCKED` ou `NOT_APPLICABLE`.
- Obsidian: `product-forge` executou `55` testes direcionados de vault,
  segurança, rollback e boundary; `forge-obsidian` foi construído como wheel e
  sdist e instalado em venv limpo, com import isolado confirmado.

### Revalidação adicional — 2026-11-10

- Product Forge `77dde99`: suíte completa `291 passed, 1 skipped`, Ruff limpo e
  CI remoto `42729793620` verde.
- O benchmark observável passou novamente em `100/1.000/10.000` notas com
  `10.000/10.000` wikilinks resolvidos e RSS residente capturado por operação;
  no tamanho máximo, o pico foi aproximadamente `131 MiB` na importação e
  `116 MiB` no SQLite/FTS. A evidência está em
  `knowledge-observability-20261110.json`.
- O E2E federado foi reexecutado contra as árvores atuais: 4 notas exportadas,
  4 round-trippadas, 4 contratos validados, Bridge autorizado, conflito manual
  detectado e nenhum corpo persistido nos outputs federados. O smoke de
  interoperabilidade permaneceu `PASS` sem vazamento de corpo.
- A bateria de federação/contratos foi reexecutada com os seis adapters
  disponíveis no workspace (`test_schemas`, `test_fuzz_contracts`,
  `test_federation_adversarial`, `test_federation_conformance` e
  `test_federated_trace`): progresso até `100%`, exit code `0`. O harness de
  conformance passou a propagar automaticamente os seis `src` de adapters para
  os subprocessos; o mesmo comando padrão agora passa sem instalação manual ou
  `PYTHONPATH` externo. A execução anterior sem essa preparação falhou
  honestamente com `ModuleNotFoundError` e não foi contada como evidência.
- O `test_capability_catalog_doc.py` também passou (`30` casos), cobrindo a
  correspondência bidirecional entre capabilities/actions expostas pelos
  adapters e o catálogo documental.

Esses resultados atualizam a prova local, mas não removem os limites externos
descritos no G12.

### Evidência cloud AWS — smoke controlado

Com autorização explícita do operador e no perfil `sparkforge`, foi criado um
único bucket S3 temporário em `us-east-1`, marcado com `Owner=the-forge`,
`Purpose=phase2-aws-profile-fix` e `ExpiresAt`. Um Parquet de 749 bytes com duas
linhas foi enviado para um único objeto. O comando executado foi:

```powershell
uv run --extra aws --extra parquet sparkforge-aws collect parquet-footer `
  --repo <temp-repo> `
  --prefix s3://<bucket-temporario>/fixtures/ `
  --max-files 1 --profile sparkforge --region us-east-1 `
  --now 2026-11-09T11:37:51Z
```

Resultado observado: `status=ok`, `files_seen=1`, `files_read=1`, `num_rows=2`,
`num_columns=2`. O objeto foi removido, o bucket foi excluído, `list-buckets`
não encontrou nenhum bucket `theforge-phase2-*` e `get-bucket-location` do nome
exato removido retornou `NoSuchBucket`. Nenhum recurso de compute, Glue, EMR,
Athena, IAM, KMS ou rede foi criado.

O smoke também encontrou e corrigiu a lacuna de ergonomia: PyArrow não aplicava
confiavelmente `AWS_PROFILE` sozinho no Windows, e o perfil AWS CLI Login
exigia `awscrt`. O `spark-forge-aws` agora aceita `--profile/--region` no
coletor e instala `boto3[crt]`; credenciais não entram no artefato nem no
comando de recoleta.
