# Versionamento e compatibilidade

The Forge versiona cinco coisas diferentes, cada uma com regra própria. Mudar uma não muda as outras: um adapter novo não muda o protocolo, e um campo opcional novo num contrato não muda a versão do schema.

## Versão de pacote
- Vale para `theforge` (`theforge.__version__`) e para os adapters `theforge-sparkforge-adapter` e `theforge-apiforge-adapter` (`version` no `pyproject.toml` de cada um, igual ao `VERSION` do pacote).
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

| The Forge | Forge Protocol | theforge-sparkforge-adapter | sparkforge-aws | theforge-apiforge-adapter | apiforge | Suporte até |
|---|---|---|---|---|---|---|
| 0.1.0 | `forge/v1` | 0.1.0 | `>=0.5.0,<0.6.0` | 0.1.0 | `>=0.1.0,<0.2.0` | lançamento de 0.3.0 |

## Regra de manutenção
- Toda wave ou release que altera `theforge.__version__` acrescenta a linha da nova versão nesta matriz **no mesmo commit**.
- Toda mudança na versão de um adapter ou no seu `SUPPORTED_SPECIALIST` atualiza a linha da versão atual de The Forge no mesmo commit.
- `tests/test_compat_matrix.py` confere a matriz contra o código: linha para `theforge.__version__`, versões dos adapters iguais às dos `pyproject.toml`, janelas iguais a `SUPPORTED_SPECIALIST` e major de protocolo em `SUPPORTED_PROTOCOLS`. A falha nomeia a versão sem linha e cita esta regra.
- Mudar a versão de The Forge é gatilho de revalidação para as waves seguintes.
