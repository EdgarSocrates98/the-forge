# ADR 0034 — Registry sources: abstração de origem, local sempre autoritativo

- Status: aceito (2026-10-07)
- Cycle 4, Wave C — phases 15–18, 20–21, 25, 30, 34

## Contexto

O Cycle 4 abre federação: descobrir providers que **não** estão instalados
exige uma noção de "registry remoto" — catálogo de metadata publicado por
terceiros. Isso é perigoso por definição: metadata remoto é input não
confiável (§18), e confundi-lo com o registry local (que valida manifest hash,
surface fingerprint e trust) criaria um canal de supply-chain.

## Decisão

1. **Duas famílias de contratos, separadas por design.**
   `ProviderEntry`/`RegistryRecord` (instalados, verificados, roteáveis) e
   `ForgeRegistryEntry`/`RegistryDocument` (publicados, declarados,
   inertes). Nenhuma API converte o segundo no primeiro — instalação é um
   plano explícito de outra wave (Wave F), não um efeito colateral de leitura.

2. **`RegistrySource` como Protocol, não classe base.**
   `read() -> SourceRead`; um source só produz `RegistryDocument`. O primeiro
   concreto é `local-file` (offline por natureza: mirrors, vendored feeds,
   air-gap). `http` é um `kind` declarável já na configuração, mas retorna
   `unavailable` até a Wave D — configuração futura não quebra o presente.

3. **Opt-in estrito.** `SourceSpec.enabled` default `false`. Fonte
   desabilitada é reportada como `disabled`, nunca lida. Precedência igual a
   `providers.toml`: user `registries.toml` primeiro; o do projeto só
   acrescenta ids novos (um projeto clonado não pode ligar fontes remotas nem
   sobrescrever a definição do usuário).

4. **Decode tolerante, fronteira explícita.** Registry documents são dados
   externos: `from_dict` tolerante a campos desconhecidos (forward-compat —
   uma fonte nova não quebra clientes antigos), mas campos *conhecidos* são
   validados (schema, provider id, SemVer, sha256, formato de plataforma).
   Falha vira `SourceRead(status="invalid")` com detalhe redacted — nunca
   exceção atravessando a fronteira.

5. **O local é uma fonte também.** `local_document(records)` projeta o
   registry instalado no mesmo formato (`local`, authoritative) — mas a
   projeção vem de manifests verificados, e seu `publisher` sintético
   (`local:<id>`) deixa explícito que não é identidade de publisher real.

6. **Sem heurística de confiança.** Nada em uma entry — nem `publisher`,
   `signatures`, `repository` ou `license` — altera trust, roteabilidade ou
   permissão. São claims declarados para discovery/negociação humana (e para
   a verificação da Wave F), nunca decisões.

## Consequências

- Gate da wave: comportamento local **inalterado** — `Registry`, cache, trust
   e routing não tocam `sources` em nenhum caminho; a camada só é exercida por
   `registry sources` (read-only) e pelos testes.
- Wave D pluga o cliente http (cache + freshness + etag/sha) implementando o
   mesmo Protocol; Wave E consome `RegistryDocument` para discovery por
   `CapabilityRequirement`; Wave F transforma candidato escolhido em
   `InstallationPlan` com aprovação.
- `RegistryDocument` rejeita providers duplicados — uma fonte não pode declarar
   duas verdades para o mesmo nome.
- `unavailable`/`invalid`/`disabled` são dados reportáveis na UX — fonte que
   falha não derruba o core (§20).
