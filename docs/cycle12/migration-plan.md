# Migration plan (Cycle 12 §2.4)

Estado alvo: GitHub=source, PyPI=runtimes Python, npm=forge-cli,
workspaces=ambientes de uso.

O que já migrou (ordem segura adotada):
1. Wheel-first como padrão de instalação (`install.sh|ps1`,
   `forge-cli install` registry-first; editable/git só opt-in).
2. Camada `_data`/`evals_data`/`platformforge/data` empacotada nos 7
   runtimes + resolvers zipimport-safe (cwd → checkout-marker →
   packaged).
3. Registries: canonical `~/.forge/installations` + bridge forge-cli
   `~/.forge-cli/forges/state.json` → lifecycle unificado
   (INSTALLED→CONFIGURED por evidência; dedup canônico-vence).
4. Launchers: `~/.forge-cli/bin/<cli>` shims por install registry.
5. Versionamento: trilha única por componente
   (`ecosystem-compatibility.json` gateado).
6. Portal: `portal_core` vendored ×7 byte-parity, assets com manifest
   sha256.

Passos restantes (exigem ambiente/credencial):
- CI runners Windows/macOS para a matriz de certificação 12.11.
- Publicação real PyPI/npm (12.12) + verificação install-from-index.
- data-sentinel-forge rollout (após o outro agente terminar).
