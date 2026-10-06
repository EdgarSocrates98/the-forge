# Versionamento e compatibilidade

The Forge versiona cinco coisas diferentes, cada uma com regra própria. Mudar uma não muda as outras: um adapter novo não muda o protocolo, e um campo opcional novo num contrato não muda a versão do schema.

## Versão de pacote
- Vale para `theforge` (`theforge.__version__`) e para os adapters `theforge-sparkforge-adapter`, `theforge-apiforge-adapter`, `theforge-doctordata-adapter` e `theforge-doctorapi-adapter` (`version` no `pyproject.toml` de cada um, igual ao `VERSION` do pacote).
- [SemVer 2.0.0](https://semver.org/): `MAJOR.MINOR.PATCH`. Antes de 1.0, um minor novo pode quebrar compatibilidade; patch nunca quebra.
- Os adapters têm release própria, independente de `theforge` ([ADR 0014](adr/0014-provider-adapter-location.md)). A compatibilidade entre eles é a da [matriz](#matriz-de-compatibilidade).

## Versão de protocolo
- Forma `forge/vN` (hoje `forge/v1`). O core aceita os majors em `SUPPORTED_PROTOCOLS` e negocia o maior major comum ([protocol.md](protocol.md)).
- Mudança incompatível no protocolo (op, envelope, semântica de exit code) exige major novo (`forge/v2`). Acréscimo compatível não muda a versão.
- Um core novo pode suportar mais de um major ao mesmo tempo durante a transição.
- `theforge provider check -- <argv>` certifica um provider contra o protocolo que o core fala hoje (`forge/v1`): a bateria recusa envelope fora do contrato e protocolo estranho ([kit de conformidade](provider-authoring.md#certificação)).

## Versão de schema de contrato
- Cada contrato persistido ou trocado carrega `schema = "theforge/<Name>/vN"`.
- Campo opcional novo, com default que preserva o comportamento anterior, **não** muda a versão. Remover campo, tornar campo obrigatório ou mudar o significado de um campo exige `vN+1`.
- Toda mudança de contrato regenera `schemas/` (`python -m theforge.contracts.schema schemas`).

## Versão de provider
- `ForgeManifest.version` é obrigatório e precisa ser SemVer 2.0.0 (sem `v` inicial, sem zeros à esquerda, ASCII). Versão malformada deixa o provider `invalid`, fora do routing, com `FORGE-MANIFEST-VERSION`.
- Toda response repete a versão em `producer.version`.
- Um adapter declara em `SUPPORTED_SPECIALIST` a janela de versões do Forge especialista que ele traduz. Especialista fora da janela → health `degraded` com a versão encontrada e a janela esperada.

## Evolução de capability
- Uma capability publicada não muda de significado. Comportamento incompatível vira **capability nova**, com id novo.
- A antiga é marcada `deprecated = true` e, quando houver substituta, `replaced_by = "<id novo>"`. O routing a mantém roteável e registra a depreciação nas notas.
- Renomeação usa `aliases`: o id antigo continua atendendo pedidos explícitos e resolve para o id canônico.
- Regras de nome e granularidade: [capabilities.md](capabilities.md).

## Janela de suporte
- The Forge suporta a versão atual e o minor anterior. Uma linha da matriz deixa de ser suportada quando sai o segundo minor seguinte (coluna `Suporte até`).
- Antes de 1.0, cada adapter suporta **um** minor do Forge especialista por vez. Sair um minor novo do especialista exige regravar o snapshot do adapter, ajustar `SUPPORTED_SPECIALIST` e atualizar a matriz.

## Matriz de compatibilidade
Fonte única. As colunas dos especialistas mostram a janela `SUPPORTED_SPECIALIST` de cada adapter.

| The Forge | Forge Protocol | theforge-sparkforge-adapter | sparkforge-aws | theforge-apiforge-adapter | apiforge | theforge-doctordata-adapter | forge-doctor-data | theforge-doctorapi-adapter | forge-doctor-api | Suporte até |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.1.0 | `forge/v1` | 0.1.0 | `>=0.5.0,<0.6.0` | 0.1.0 | `>=0.1.0,<0.2.0` | — | — | — | — | lançamento de 0.3.0 |
| 0.2.0 | `forge/v1` | 0.2.0 | `>=0.5.0,<0.6.0` | 0.3.0 | `>=0.1.0,<0.2.0` | 0.3.0 | `>=1.0.0rc1,<2.0.0` | 0.3.0 | `>=0.2.0,<0.3.0` | lançamento de 0.4.0 |

## Identidade de superfície
`version` não é identidade: a mesma versão pode carregar uma superfície diferente (observado em sparkforge 0.5.0 e apiforge 0.1.0). O contrato `theforge/ProviderSurfaceIdentity/v1` pareia as versões declaradas com dois fingerprints determinísticos que o core computa do manifest em uso:

- **`capability_fingerprint`**: sha256 sobre o conjunto de capabilities — id, actions, `default_action`, `state`, `operation_class`, tiers de `context`, flags `accepts_handoff`/`proposes_plans`/`resolves_ambiguity`, `aliases`, `deprecated`/`replaced_by` e `relations`.
- **`surface_fingerprint`**: o capability fingerprint mais `ops`, `protocols`, `features`, `execution`, `context_revalidation` e `domains` declarados.
- **`native_surface_fingerprint`**: declarado pelo provider (`manifest.native_surface_fingerprint`) — nos adapters, o sha256 do snapshot nativo empacotado. Hash é evidência, não confiança.

Os fingerprints excluem `id`/`version`, `description`/`signals` (apresentação e roteamento, não forma operacional), `limitations`/`unknowns` e qualquer valor de máquina ou timestamp — `recorded_at` é o instante em que o core observou a identidade e nunca entra num fingerprint.

Onde aparecem: o `RegistryRecord` carrega a identidade inteira; o cache do registry guarda e confere os dois fingerprints (arquivo corrompido ou adulterado é descartado); `providers health` e `doctor` mostram `surface:<prefix>`; o receipt do run grava `provider.surface_fingerprint`/`native_surface_fingerprint`; `replay` e `resume` recusam ou marcam drift quando a superfície gravada diverge da atual — mudança de superfície com a mesma versão deixa de ser invisível.

## Features de protocolo
`manifest.features` declara ids `"<nome>/v<major>"` (ex.: `handoff/v1`). O core nunca assume feature: ausente significa *não negociado* e o ponto de uso degrada — limitação, passo pulado ou pedido mais estreito — nunca quebra. O kit de conformidade falha quando um feature conhecido é declarado sem a superfície que o sustenta (ex.: `verify/v1` sem a op `verify`); ids bem-formados que o core não conhece são ignorados, então um provider mais novo pode declarar `delta/v2` contra um core antigo.

`supports(manifest, feature)` resolve contra o declarado ∪ implícito: `accepts_handoff` já implica `handoff/v1`, a op `verify` já implica `verify/v1`, `proposes_plans` implica `plan-proposal/v1`, `resolves_ambiguity` implica `resolve/v1` — manifests antigos continuam completos sem declarar nada.

Vocabulário conhecido deste core: `handoff/v1`, `verify/v1`, `plan-proposal/v1`, `resolve/v1`, `semantic-handoff/v1`, `economy-receipt/v1`, `trace-ref/v1`, `resume/v1`, `delta/v1`, `graph-refs/v1`.

## Regra de manutenção
- Toda wave ou release que altera `theforge.__version__` acrescenta a linha da nova versão nesta matriz **no mesmo commit**.
- Toda mudança na versão de um adapter ou no seu `SUPPORTED_SPECIALIST` atualiza a linha da versão atual de The Forge no mesmo commit.
- `tests/test_compat_matrix.py` confere a matriz contra o código: linha para `theforge.__version__`, versões dos adapters iguais às dos `pyproject.toml`, janelas iguais a `SUPPORTED_SPECIALIST` e major de protocolo em `SUPPORTED_PROTOCOLS`. A falha nomeia a versão sem linha e cita esta regra.
- Mudar a versão de The Forge é gatilho de revalidação para as waves seguintes.
