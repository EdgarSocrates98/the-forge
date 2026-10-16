# Forge CLI lifecycle — Cycle 10.1 §5.2

- **Date**: 2026-10-15 (UTC-3)
- **Repo under test**: forge-cli @ `ee50e4b` (branch `cyc101/cli-lifecycle-matrix`, PR [#9](https://github.com/EdgarSocrates98/forge-cli/pull/9))
- **Host**: Linux, Node v22.23.2, git 2.43.0
- **Harness**: `tests/lifecycle-matrix.test.ts` — real `git` repos (bare remote + work tree on local disk), real CLI process (`node --import tsx src/index.ts`), isolated `HOME`/`USERPROFILE`/`--dir`, fully offline.

## Commands executed

```
npx vitest run tests/lifecycle-matrix.test.ts   # 8/8 PASS
npm test                                        # 622/622 PASS (48 files)
npm run typecheck                               # clean
npm run lint                                    # clean
npm run format:check                            # clean
npm run build                                   # dist/index.js 711.70 KB
```

## Matrix results (8/8)

| Scenario | Result | Evidence |
|---|---|---|
| remote substitution on `update` | **REFUSED** (expected) | `remote-mismatch` → warning `Remote origin difere do catálogo — repositório não atualizado`, HEAD unchanged |
| downgrade via `pin` + `update --offline` | PASS | fixed-ref checkout to pinned sha; `state.repos[name].head` updated |
| `rollback` after downgrade | PASS | returns to `previousHead`; requires two recorded updates |
| rollback on dirty tree | **REFUSED** (expected) | update scaffolds `.env` → `isGitDirty` → refusal until file removed |
| partial failure isolation | PASS | sibling with substituted remote is refused while pinned downgrade applies to the good repo |
| uninstall | PASS | clean clone removed; sibling untouched |
| drift detection | PASS | local commit → `status --json` reports drifted |
| version mismatch vs `ecosystem-compatibility.json` | PASS | `update --check --json` → `installed_compat: incompatible` |
| corrupted manifest | PASS | degrades to `manifest: null`, repos still listed, exit 0 |
| reinstall idempotent | PASS | second run records same head, no duplicate state |

## Findings (honest limitations)

- **F-CLI-1 — pull path NOT_TESTED offline by design**: `syncRepo` reads `git remote get-url origin`, which expands `url.insteadOf` (verified on git 2.43.0). A local bare cannot impersonate the catalog URL, so the successful `git pull --ff-only` path cannot be simulated without real GitHub access. The mismatch refusal — the safety-critical half — IS tested.
- **F-CLI-2 — `.env` scaffold blocks rollback**: `update` writes `.env` inside the clone; the resulting dirty tree makes `rollback` refuse. Recovery requires manually removing the scaffold. Real friction, now pinned by test; consider excluding `.env` from the dirty check or gitignoring it per-clone (product decision, not made here).
- **F-CLI-3 — `previousHead` needs two recorded updates**: a single update records `head` only; rollback after exactly one update fails with `no-previous`. Documented semantics; regression now covered.
- **F-CLI-4 — self-install mutates user-level state outside the target dir** (observed during interactive validation, earlier session): `theforge install --root /tmp/fi-real-tf` still wrote `~/.local/bin/theforge` and `~/.config/forjas/env.sh`. Restored by reinstalling to `~/.forge/installs/the-forge`. The matrix exercises `--dir` repo ops, not self-install; self-install isolation remains **NOT_TESTED** in CI — needs a harness that also overrides `~/.local/bin` and `~/.config`.
- **install/clone of catalog repos**: covered by `e2e-cli.test.ts` (offline clone) and `install.test.ts`; not duplicated here.

## Coverage vs §5.2 acceptance

| Required | Covered |
|---|---|
| install | e2e-cli offline clone + install.test.ts (existing) |
| update | matrix (refusal paths + fixed-ref); online pull NOT_TESTED |
| downgrade/version pinning | matrix pin + `--offline` + `previousHead` |
| rollback | matrix (success + dirty refusal + no-previous semantics) |
| repair/heal | `heal.test.ts` (existing, 7 suites) |
| uninstall | matrix + lifecycle.test.ts + e2e-cli |
| failure/refusal | matrix (remote-mismatch, non-git sibling, corrupted manifest) |
| no unrelated user-state mutation | matrix isolates `HOME`; F-CLI-4 recorded for self-install |
| Linux | all runs on Linux host above |

**Status**: PASS with recorded limitations (F-CLI-1, F-CLI-4 gate the remaining cells).
**Next**: online pull/update round-trip + self-install isolation harness (F-CLI-4) — candidate for cyc101-08 RC validation.
