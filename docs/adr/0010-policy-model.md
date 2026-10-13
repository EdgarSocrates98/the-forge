# ADR 0010 — Modelo de policy e diferença concreta entre níveis de trust

- Status: aceito (2026-10-03)

## Contexto
No ciclo 1, `trusted` e `local` só diferiam no desempate de routing. Execuções não tinham decisão de risco: uma capability destrutiva rodava como qualquer outra.

## Decisão
- Antes de iniciar o provider, o core produz uma decisão `allow | ask | deny` e grava o artefato `risk` no run. As dimensões vêm da declaração do provider (`operation_class`; `requires_network = true` força `external_read`); `credentials` e `cross_account` ficam `unknown`.
- Vale a regra **mais severa** (`allow < ask < deny`) entre as dimensões `yes`. Nenhuma dimensão `yes` resulta em `deny` defensivo. Uma regra ausente na configuração também resulta em `deny`.
- Regras padrão: `read_only = allow`, `local_mutation.builtin = allow`, `local_mutation.trusted = allow`, `local_mutation.local = ask`, `local_mutation.unverified = ask`, `external_read = ask`, `external_mutation = ask`, `destructive = deny`.
- O nome da regra registrado é `<origem>.<chave>`, com origem `default|user|project`. O `policy.toml` do usuário pode afrouxar ou endurecer. O `.forge/config/policy.toml` do projeto só endurece, e tentativas de afrouxar são ignoradas com aviso.
- `ask` sem aprovação resulta em `refused` com `POLICY_APPROVAL_REQUIRED` e `unlock = "--approve <capability>"`. `ask` aprovado vira `allow` com `approved = true`. `deny` resulta em `refused` com `POLICY_DENIED` e nunca é satisfeito por aprovação, então `destructive` não executa nem com `--approve`.

## Diferença concreta entre níveis
- `builtin`: reservado ao core; só o eco embutido. Roteável; `local_mutation` → `allow`.
- `trusted`: concedido só no `providers.toml` do usuário. Roteável; `local_mutation` → `allow`.
- `local`: concedido só no `providers.toml` do usuário. Roteável; `local_mutation` → `ask`.
- `unverified`: padrão, e o único nível de entradas de projeto (um `trust` maior no `providers.toml` do projeto é rebaixado com aviso). Só roteia com `--allow-unverified`; `local_mutation` → `ask`; nunca entra no cache.
- `blocked`: nunca roteia nem executa. É filtrado antes da policy.
- Além da policy, a única diferença entre `trusted` e `local` é o desempate quando vários providers declaram a capability pedida com `--capability`: ordem `builtin < trusted < local < unverified`, depois id.

## Alternativas
- **Policy embutida no router:** mistura WHO com governança.
- **Fundir `trusted` e `local`:** quebra configs existentes e perde a distinção entre "confio para mudar arquivos" e "confio para rodar".

## Consequências
`local` passa a significar "roda, mas pede aprovação para mutação local". Intenção futura (4.2): `trusted` deve ser o nível que acumula garantias e permissões adicionais (candidatos: exigir a identidade forte do ADR 0013, regras próprias por trust para dimensões além de `local_mutation`), e `local` o nível de uso diário sem elas. Se nenhuma diferença nova se justificar, o modelo deve ser simplificado, fundindo os dois níveis. A classificação é uma declaração do provider, não enforcement (ADR 0012).
