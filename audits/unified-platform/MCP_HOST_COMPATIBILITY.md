# MCP Host Compatibility — 2026-11-13T05:23:18+00:00

Stdio JSON-RPC handshake measured live (perf-baseline.json `mcp_handshake`):

```json
{
  "data-sentinel-forge": {
    "init_ms": 1586,
    "tools": 22,
    "tools_list_ms": 2
  },
  "platform-forge": {
    "init_ms": 118,
    "tools": 39,
    "tools_list_ms": 1
  },
  "spark-forge-aws": {
    "init_ms": 1935,
    "tools": 148,
    "tools_list_ms": 24
  },
  "the-forge": {
    "init_ms": 1489,
    "tools": 15,
    "tools_list_ms": 1
  }
}
```

initialize/initialized/tools-list/tools-call verified against real server
subprocesses in operational E2E (scenario E-mcp-*).
