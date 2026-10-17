# Cycle 11.2 — Offline integrity (P2-001)

Escopo: integridade de instalação `--offline` no método registry do
forge-cli — artefatos da dist vs. fecho transitivo.

## Comandos executados

```text
git show origin/main:src/registry/install.ts | grep -n "sha256\|offline\|find-links\|lock"
git status --short   # working tree feat/c11-2-bc — lock.ts uncommitted
head -50 src/registry/lock.ts
git diff -- src/registry/install.ts src/cmd/registry.ts src/cli-args.ts
```

## Estado em main (6ea2e79)

- Artefatos da **dist** conferidos byte a byte: sha256 do wheel/sdist no
  cache vs. digest do PyPI — divergência → `hash-mismatch` + arquivo
  movido para `*.rejected` (quarentena) + sem venv/state
  (`install.ts:305-333`).
- `--offline` exige artefatos presentes no wheel cache — ausente →
  `offline-missing-artifact` honesto, nunca finge instalar sem rede.
- Cache PyPI tem TTL + `staleCache` marcado no receipt quando o fallback
  usa cache expirado.
- **Limite conhecido e documentado no código** (`install.ts:543-544`):
  "offline, deps transitivas resolvem por nome no --find-links sem pin
  de hash" — o `--find-links` aponta para o wheel cache, mas uma
  dependência adulterada no cache não é detectada. Era exatamente o gap
  P2-001.

## In-flight (feat/c11-2-bc, uncommitted — worker C)

`src/registry/lock.ts` novo (+~250 linhas): formato
`forge-cli-offline-lock/1` — fecho transitivo de uma dist PyPI gerado
por `pip download --report` ONLINE uma vez:

```text
generateOfflineLock → { forge, dist, version, python, platform,
                        generatedAt, artifacts: [{name, version,
                        filename, sha256, python_tag, platform_tag,
                        source}] }
```

- `registry lock <forja…>` (novo sub-verbo, `--out <arquivo|dir>`):
  resolve online, gera `<forja>.offline-lock.json` via `writeFileAtomic`.
  Exige rede — erro nomeado se chamado offline.
- `install --offline --lock <file>`: valida o lock INTEIRO antes de
  qualquer mutação — artefato faltando, hash divergente, extra no cache
  ou tag incompatível → recusa pura, sem venv nem escrita.
- 9 `LockError` kinds nomeados: `lock-invalid`, `lock-download-failed`,
  `lock-report-missing`, `lock-missing-artifact`, `lock-extra-artifact`,
  `lock-hash-mismatch`, `lock-incompatible-tag`, `lock-missing-dependency`,
  `lock-mismatch`. Normalização PEP 503 para Requires-Dist.
- Receipt ganha `offlineLock: { file, artifacts }` — evidência de
  instalação travada.
- Flags novas: `--lock <file>`, `--out <path>`.

Estado em captura: uncommitted no working tree; sem PR aberto.

## Veredito

IN_PROGRESS — artefatos da dist já têm pin de hash em main; o fecho
transitivo (o gap real) tem implementação e formato definidos, ainda
não mergeados.

## Risco residual

Em main, uma dependência transitiva trocada no wheel cache passa pelo
`--find-links` sem verificação — vetor real mas limitado a quem já tem
escrita no home do usuário. Lock é por plataforma/interpreter — lock
gerado em linux/3.12 não serve para windows/3.13 (declarado, não bug).
