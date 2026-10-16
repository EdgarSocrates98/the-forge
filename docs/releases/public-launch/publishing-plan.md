# Release 1 — Plano de publicação (executar SÓ após aprovação)

## Ordem (dependências reais, não artificiais)

Especialistas e ferramentas são independentes entre si — podem publicar
em paralelo. Sequência sugerida por conveniência de validação:

1. **Tags git** (`v<ver>`) nos 9 repos — commit de release exato.
2. **GitHub Releases** nos 9 repos — notas + assets (wheels, sdists,
   tarball npm, SHA256SUMS, SBOM).
3. **PyPI** — 7 pacotes via Trusted Publishing OIDC.
4. **npm** — `theforge-cli` (`npm publish --provenance`).
5. **Verificação externa** (Wave 11) — instalar dos registries em
   ambiente limpo e validar.

## Assets por release

- the-forge: `the_forge-0.5.0-py3-none-any.whl`, `the_forge-0.5.0.tar.gz`,
  `SHA256SUMS.txt`, `sbom.cdx.json`.
- forge-cli: `theforge-cli-0.1.0.tgz`, checksum, notas.
- Especialistas: `<dist>-<ver>-py3-none-any.whl` + `.tar.gz` + checksums.
- forge-portal: distribuído via wheel the-forge (sem asset separado).

## Trusted Publishing — configuração prévia (ação humana)

1. PyPI: criar projeto + Trusted Publisher apontando
   `EdgarSocrates98/<repo>` + workflow `publish.yml` + environment
   `pypi` (OIDC).
2. npm: habilitar provenance ou granular token.

## Pendências externas (bloqueiam publicação)

- Aprovação explícita do mantenedor (`approval-checklist.md`).
- Configuração PyPI/npm Trusted Publishing pelo mantenedor.
- Decisão final sobre nomes (`the-forge` vs `theforge-core`;
  `theforge-cli` vs escopo).
- Promoção `forge-doctor-data 1.0.0rc1 → 1.0.0` se aprovada.
