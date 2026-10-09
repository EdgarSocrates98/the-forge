# ADR 0058 — Instalação portátil: kit vendored, escopos e família

- Status: aceito (2026-10-09)

## Contexto

O programa de instalação portátil (prompt_evo_install) pede que cada Forge
seja instalável de qualquer diretório: *clone once, setup once, install
anywhere*. ADR-0055 já governava o bootstrap de *providers* (conhecimento →
plano → aprovação → verificação); faltava o ciclo de vida dos *assets de
host* — skills, agents, `.mcp.json`, marcadores — no repositório consumidor,
mais a orquestração da família (`theforge install auto`).

Sem subsistema próprio, cada forge improvisaria o seu — sete interpretações
de posse, recibo e reversibilidade. A decisão de ADR-0020 (assets agentic
nunca ship) também precisava de emenda: sem árvore bundled, `install` a
partir de wheel não teria fonte canônica.

## Decisão

1. **Kit canônico vendored**: `scripts/installkit/forge_installkit.py` é a
   fonte única (stdlib-only, ADR-0003 preservado). Cada forge carrega uma
   cópia byte-idêntica — `theforge._installkit` aqui — em vez de depender
   de runtime cruzado entre repos. Divergências entram pelo canônico, nunca
   por fork local.
2. **Contrato `forge/*` versionado** em `docs/portable-installation/`:
   `InstallationManifest/v1`, `InstallReceipt/v1`, `InstallationHealth/v1`,
   `WorkspaceInstall/v1`. Planejar nunca executa; executar exige `--yes`
   explícito (`FORGE-INSTALL-PLAN-NOT-APPROVED`); `'latest'` é recusado.
3. **Escopos**: `project` (raiz do VCS), `workspace` (raiz do workspace
   manifest), `user` (HOME). Estado do projeto em `.forge/install/`
   (ledger sha256, receipts, lock O_EXCL) — separado de `.forge/` runtime.
4. **Posse**: o ledger registra sha256+kind por arquivo gerenciado;
   arquivo pré-existente do usuário é adotado ou pulado, nunca sobrescrito
   em silêncio; `uninstall` remove só o que o ledger declara `managed`.
   Marcadores são blocos delimitados `the-forge:managed`, excisão segura.
5. **`install auto`**: lê `~/.forge/installations/*.json` (o registry que
   o bootstrap escreve) e delega `install` ao CLI de cada forge instalado —
   o control plane coordena, cada forge executa a si mesmo. CLI ausente
   vira `BLOCKED`, nunca simulado.
6. **Emenda a ADR-0020**: `.agents/skills` passa a entrar no wheel sob
   `theforge/host_assets/skills` (e no sdist na raiz) — é o que `install`
   lê sem checkout. A exclusão de `.claude`, `.devin`, `.kiro` permanece:
   são espelhos e estado local, não fonte canônica.

## Consequências

- O ciclo de vida `install/status/doctor/repair/uninstall` é idêntico em
  todas as forges — uma implementação, sete pacotes.
- `install plan` (providers) e `install` (assets de host) coexistem: um
  instala especialistas no registry do the-forge, o outro instala as
  forges no repositório do usuário.
- O gate de aprovação é o mesmo de ADR-0055 — aprovação nunca produzida
  pela própria instalação.
