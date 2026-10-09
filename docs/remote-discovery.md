# Remote Discovery

Descoberta opcional de providers que **não** estão instalados, por
`CapabilityRequirement` (§22-26, ADR 0036).

```text
Task → CapabilityRequirement → negotiate_all(instalados)
   ├─ FULL   → satisfeito localmente — fontes remotas nem são lidas
   └─ não-FULL → fontes habilitadas (registries.toml)
                 → evaluate_entry por ForgeRegistryEntry
                 → RemoteProviderCandidate/v1
                 → fim. Nenhuma ação é tomada.
```

**Discovery não é instalação.** Um candidato é metadata declarada: existência,
versão, publisher declarado, distribuição, assinaturas *declaradas* (nunca
verificadas nessa camada), freshness. Instalação é a Wave F — plano explícito,
hashes, aprovação.

## CLI

```text
theforge capabilities discover --capability security.scan
theforge capabilities discover --requirement req.json [--remote] \
    [--profile economy|balanced|max] [--json]
```

- `--capability` monta um requirement mínimo; `--requirement` carrega o
  documento completo (actions, technologies, offline, platforms…).
- `--remote` força a consulta mesmo quando um provider local já satisfaz —
  útil para comparar fit antes de trocar de fornecedor.
- `--profile` (Wave G) controla quando a consulta remota acontece
  (§48): `economy` só quando nenhum provider local declara a capability,
  `balanced` (default) só quando nada local satisfaz `FULL`, `max`
  sempre compara claims remotos.
- Exit code 0 sempre: descoberta é informação, não veredito de execução.

## Economia da descoberta (§47)

O report mede o próprio custo: `registry_calls` (fontes que serviram
documento), `metadata_bytes` (bytes consumidos — inclui cache) e
`network_ms` (latência real de rede; `null` quando só cache/local-file).
Consultas repetidas usam o cache fresco — `freshness`/`from_cache` em cada
candidato mostram o que foi rede e o que foi disco.

## Saída (texto)

```text
local: UNSUPPORTED — no installed provider fully satisfies 'security.scan'
Remote candidates:
  1. security-forge 1.3.2 (source=feed registry=team-reg fresh) — fit=declared
     publisher=acme; distribution=pip-package security-forge==1.3.2; signature declared (unverified)
     limitation: linux only
No action was taken.
```

## Fit remoto: honesto por construção

Um `ForgeRegistryEntry` declara ids, runtime e plataformas — não actions,
evidência nem surface. Logo o fit remoto tem teto em `declared`:

| `fit` | significado |
|---|---|
| `declared` | a entry lista a capability e nenhuma dimensão exigida está faltando ou não-declarada |
| `partial` | declara a capability, mas há demands faltantes ou campos não-declarados (`unknowns`) |
| — | sem a capability → nem candidato; contradições duras → `entries_excluded` com a razão |

Candidatos carregam `matched`/`missing`/`unknowns` explícitos —
`unknowns: ["required_actions:remote-undeclared"]` é a resposta honesta para
o que metadata remota não pode provar. `signature_state` só tem `none` e
`declared` nesta camada (verificação é da Wave F); `freshness` espelha o
`SourceRead` (`fresh`/`stale`/`unknown` para `local-file`).

## Filtros do requirement (§23)

| campo do requirement | avaliado na entry |
|---|---|
| `capability` | presença em `entry.capabilities` (admissão) |
| `technologies` | interseção com `entry.technologies`; undeclared → unknown |
| `platform_constraints` | `entry.platforms` (`"any"` satisfaz tudo; vazio → undeclared) |
| `offline_required` / `network_allowed=false` | contradizem `runtime.requires_network` → excluído |
| `credentials_allowed=false` | contradiz `runtime.requires_credentials` → excluído |
| `required_actions`, `required_evidence`, `protocol_features`, `operation_class_ceiling` | não declaráveis em v1 → `unknowns` |
| protocolos | `forge/v1` ausente → `missing` (floor de instalabilidade) |

## Ordenação determinística

`declared` antes de `partial`, depois provider id, versão SemVer desc,
registry id. Popularidade, downloads e stars **nunca** ordenam candidatos.

## Fronteiras

- Nada instala, executa ou ganha trust — `action_taken: false` no `--json`.
- Fonte `http` obedece às regras da Wave D: opt-in, https-only, cache
  verificado, `THEFORGE_NO_NETWORK`, `stale` explícito.
- Fonte remota nunca sobrescreve o registry local — são camadas separadas.
