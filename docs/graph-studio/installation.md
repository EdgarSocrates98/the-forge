# Installation

Graph Studio is embedded in each CLI — no extra payload, no Node.js.

## Optional component

The install wizard offers an *Optional components* step (defaults follow
the profile). `graph-studio` unchecked is persisted to
`<state-dir>/components.json` as `graph_studio: false`; `graph ui` then
refuses with an unlock message. Re-run install with the component to
enable it later.

Non-interactive:

```bash
<cli> install apply --yes --components skills,mcp,tui,graph-studio
```

State dir per forge: `.forge/install`, `.apiforge/install`,
`.sparkforge_aws`, `.sparkforge-azure`, `.platformforge`,
`.forge-doctor-data/install`, `.forge-doctor-api/install`.

## Remote / headless

Use `--no-browser`; the server prints its URL. On a remote host, forward
the port (`ssh -L PORT:127.0.0.1:PORT`) — the CLI never assumes a remote
browser.
