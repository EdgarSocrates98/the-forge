# Phase 2 — Execution Report

Data: 2026-11-09. Este relatório centraliza a execução do programa de integração
Obsidian/Cycle 2.0–2.6. Evidência local usa fixtures e não autoriza inferência
de execução em cloud ou em vault de usuário.

| Gate | Estado | Evidência principal | Limitação |
|---|---|---|---|
| G0 baseline/arquitetura | PASS | `BASELINE.md`, `OWNERSHIP_MATRIX.md` | índices de código são best-effort |
| G1 correções P0/P1 | PASS | commits por Forge registrados no baseline; Product regression local 82,62%; The Forge CI `42564466899` e release-gates `42564466922` verdes | branches sem workflow publicado e demais branches especialistas ainda não têm um único run global consolidado |
| G2 contratos/schemas | PASS | `tests/test_schemas.py` e `tests/test_fuzz_contracts.py` verdes; `KnowledgeDocument/v1` agora valida `knowledge_state`; schemas Obsidian v1 | compatibilidade externa não foi exercitada |
| G3 segurança/autorização | PASS local | traversal, symlink/reparse, hardlink, classificação, raiz autorizada e prompt-safety | permissão real e vault multiusuário não executados |
| G4 formatos | PASS local | Markdown, frontmatter, links, embeds, Canvas estrutural e Bases em YAML oficial com serializer/validador de `forge_obsidian` | não é parser/runtime completo do aplicativo Obsidian; fórmulas e filtros não são executados pelo Product Forge |
| G5 integridade de sync | PASS local | Product Forge `172f4ef` — 286 passed, 1 skipped; `-m not benchmark`: 283 passed, 1 skipped, 3 deselected; `forge_obsidian` distribuível sem dependência do runtime Product Forge; wheel/sdist `forge-obsidian` construídos pelo fluxo wheel-from-sdist; plan/baseline/conflict/atomic/rollback/skip/lock, índice seguro de paths, importação governada de investigação e ciclo de conhecimento evidence-gated; fault injection explícito para disk full e permission denied | publicação remota/pin pelos adapters e falhas reais de filesystem ainda não executados |
| G6 adapters | PASS fixture | AWS, Azure, API e Platform no runner federado | sem cloud real |
| G7 recuperação agêntica | PARTIAL | processo encerrado durante temporário e recuperação subsequente verificados; falhas disk full/permission denied estruturadas e testadas por fault injection | falhas reais de filesystem pendentes |
| G8 E2E federado | PASS fixture | `FEDERATED_E2E_EVIDENCE.md`; 4 notas produzidas pelos adapters, 4 contratos `ObsidianNoteRef` validados contra schema, round-trip, Atlas, Lens, Bridge e conflito manual | não é homologação cloud/vault de usuário; runner de fixtures é separado do endpoint de investigação |
| G9 Portal/UX | PASS local | 603 testes frontend de baseline + 21 direcionados; Nova investigação com evidências, plano assinado, execução federada, recibo e handoff explícito para índice Product Forge; conhecimento com conexão, descoberta body-free de paths, preview, import/export, conflitos, histórico, ciclo de revisão e deep link Obsidian; gate visual 8/8, axe/overflow/foco = 0; pacote instalado fora do checkout com CLI/TUI/status/start estático e HTTP 200 | gravação no Obsidian continua sendo sync revisado e explícito; produção/OIDC pendentes |
| G10 instalação/distribuição | PASS local | matriz Python 12/12 wheel→venv→CLI passou no Windows e Linux WSL2; matriz limpa do wheel The Forge project/workspace/user passou com apply/uninstall; Product Forge wheel/venv/Portal fake passou; `forge-cli` e Portal Node build/pack passaram; matriz TTY/TUI 14/14 e cancelamento 14/14 verdes; MCP handshake real The Forge PASS com 15 tools e exit code 0; Product Forge publica 17 tools, incluindo índice Obsidian read-only | OIDC e matriz remota global ainda pendentes |
| G11 performance/regressão | PARTIAL | receipt observável de scan/import/wikilinks/export/reindex/search, orçamento de contexto estimado, qualidade de citações fixture e gateway com provider controlado em 100/1.000/10.000; suíte não-benchmark Product Forge `283 passed, 1 skipped, 3 deselected`; benchmark de escala `3 passed` com wall-clock observacional; importação quente direta de 10.000 notas ficou em ~6–8 s | uso real de tokens de provider `NOT_RUN`; wall-clock de filesystem recém-criado (16,90 s em uma amostra Windows) fica registrado para tendência, não como limite arbitrário; tracemalloc não é RSS |
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
- API Forge: gateway, refs, trust e projeção Obsidian: `23 passed`;
- Spark Forge AWS: claims `0 divergências`; status, evals, sincronização de
  skills e bundle offline passaram; `sparkforge-aws collect parquet-footer`
  foi homologado contra S3 real com perfil AWS CLI Login, região explícita,
  `status=ok`, 1 arquivo, 2 linhas e 2 colunas; o bucket/objeto temporários
  foram excluídos e a consulta posterior retornou `NoSuchBucket`;
- E2E federado: `notes_exported=4`, `notes_roundtripped=4`,
  `manual_conflict_detected=true`, `cloud_access=false`.

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
