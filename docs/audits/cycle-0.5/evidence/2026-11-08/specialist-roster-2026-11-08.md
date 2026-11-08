# Specialist roster evidence — 2026-11-08

Command:

```powershell
uv run forge specialists list --root E:\projetos\FORJAS --json --no-probe
```

The refreshed local catalog observed the following states:

| Provider | Install state | Roster state | Routable |
|---|---|---|---:|
| api-forge | INSTALLED | CONFORMANT | true |
| code-atlas-forge | DISCOVERED | CONFORMANT | true |
| data-sentinel-forge | DISCOVERED | CONFORMANT | true |
| forge-agent-bridge | DISCOVERED | CONFORMANT | true |
| forge-doctor-api | INSTALLED | UNKNOWN | false |
| forge-doctor-data | INSTALLED | UNKNOWN | false |
| forge-lens | INSTALLABLE | CONFORMANT | true |
| platform-forge | INSTALLED | CONFORMANT | true |
| product-forge | INSTALLED | CONFORMANT | true |
| spark-forge-aws | INSTALLED | CONFORMANT | true |
| spark-forge-azure | INSTALLED | CONFORMANT | true |
| the-forge | INSTALLED | CONFORMANT | true |

The conformant rosters are declarative, packaged assets with manifest parity;
they do not claim provider authentication or a live agent session. Those
states remain explicit in the catalog and in the Cycle 0.5 E2E report.
