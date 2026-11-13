# MCP Host Compatibility — 2026-11-13T02:45:10+00:00

Stdio JSON-RPC handshake measured live (perf-baseline.json `mcp_handshake`):

```json
{
  "data-sentinel-forge": {
    "init_ms": 1629,
    "tools": 22,
    "tools_list_ms": 2
  },
  "platform-forge": {
    "init_ms": 126,
    "tools": 39,
    "tools_list_ms": 1
  },
  "spark-forge-aws": {
    "init_ms": 2084,
    "tools": 148,
    "tools_list_ms": 25
  },
  "the-forge": {
    "init_ms": 1747,
    "tools": 15,
    "tools_list_ms": 1
  }
}
```

initialize/initialized/tools-list/tools-call verified against real server
subprocesses in operational E2E (scenario E-mcp-*).
