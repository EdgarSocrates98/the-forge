# Confirmed gaps (Cycle 12 §2.4)

Registro honesto — o que NÃO está fechado (detalhe/severidade em
`baseline.md` §5 + Rodadas):

- **Pendente — Fase G**: matriz Windows/macOS sem runners (nenhuma
  evidência nessas plataformas); publicação real PyPI/npm bloqueada
  por credenciais. Parcial ao alcance: sdist→wheel rebuild
  (`python -m build` do api-forge refez a wheel a partir do sdist) e
  E2E descartável (`/tmp/c12-e2e`: venv limpa instalou a wheel,
  `apiforge --version`/`knowledge list` → 40 packs sem checkout).
- **Pendente — data-sentinel-forge**: deferido por instrução do dono
  (outro agente evoluindo); permanece a 90c10a8 intocado.
- **Fechados em review**: credential echo em refusals (R10-11),
  SourcesError traceback (R10), AST purity doctor-api (R11), receipt
  stale (R11/R13), registry sem launcher (R12), clone-default (R12),
  registries disjuntos (R12), register-antes-de-smoke (R12),
  artifact-skip (R12), portal dual-version (R12-13), update --to em
  direct ref http/unspaced/file (R11-14), FORGE_CLI_HOME bridge
  (R14), pack traversal api-forge (R14), lockfile libc (R14).
