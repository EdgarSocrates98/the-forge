# ADR 0035 — Remote registry client: read-only, cache verificado, freshness explícita

- Status: aceito (2026-10-07)
- Cycle 4, Wave D — phases 20–21, 25, 34

## Contexto

Wave C abriu a abstração de fontes com `local-file`. A Wave D precisa do
cliente `http` real — mas qualquer fetch remoto introduz três riscos novos:
(1) o core offline-first não pode depender de rede; (2) metadata remoto
cacheado pode estar velho ou adulterado e ainda assim parecer atual; (3) um
endpoint inseguro (http, redirect, body gigante) pode virar vetor de
supply-chain antes mesmo da instalação existir.

## Decisão

1. **Read-only, só o documento.** `HttpRegistrySource` faz `GET` no `url`
   configurado — que aponta diretamente para um `RegistryDocument`. Nenhum
   POST, nenhum download de pacote, nenhuma autenticação implícita. Distribuição
   real é decisão da Wave F (InstallationPlan), não do discovery.

2. **Freshness budget por fonte.** `max_age_s` (default 3600): cache dentro do
   budget é servido sem fetch (eficiência — não chamamos remoto
   repetidamente); fora do budget, `GET` condicional com `If-None-Match` e
   `304` renova `retrieved_at` sem re-download.

3. **Stale é um estado, não um fallback silencioso.** Fetch falhou e existe
   cache expirado → `status="stale"` + documento + detalhe. A UX e a Wave E
   podem inspecionar candidatos stale, mas ninguém os confunde com frescos.

4. **Cache com integridade.** O envelope guarda `url`, `retrieved_at`, `etag`,
   `body_sha256` e o corpo bruto; na leitura o sha é recomputado e o documento
   re-decodificado. URL mudou, sha divergiu, envelope corrompido → cache
   ignorado. Cache poisoning nunca é servido silenciosamente.

5. **Transporte restrito.** `https://` obrigatório fora de loopback (`http://`
   só para `127.0.0.1`/`::1`/`localhost`); redirect é revalidado no URL final;
   body limitado a 8 MiB; timeout configurável (`timeout_s`, default 10);
   exceções de transporte viram `unavailable` com o tipo do erro — nunca
   traceback atravessando a fronteira.

6. **Duplo gate para rede.** `enabled = true` (opt-in por fonte) **e**
   `THEFORGE_NO_NETWORK` ausente. O kill-switch ambiental cobre ambientes
   air-gapped sem depender de edição de configuração; com cache válido ele
   ainda serve o documento marcando freshness corretamente.

7. **Fetcher injetável.** `Fetcher = Callable[[url, headers, timeout],
   FetchResponse]` — a suíte offline injeta fakes; o default é urllib stdlib,
   zero dependências novas (invariante do core).

## Consequências

- Gate da wave: core offline intacto — nenhum caminho de `ask`/`plan`/routing
   toca `read_sources`; o fetch só acontece em `registry sources` e, na
   Wave E, em discovery explícito.
- `SourceRead` carrega proveniência completa (`freshness`, `from_cache`,
   `retrieved_at`, `etag`, `body_sha256`) — a Wave E pode reportar freshness
   por candidato sem re-implementar contabilidade.
- Custos de rede ficam lineares em fontes habilitadas e amortizados pelo
   freshness budget — econômico por construção.
