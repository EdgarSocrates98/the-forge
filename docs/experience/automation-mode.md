# Automation mode

Every interactive surface degrades to a deterministic, scriptable path.

| Situation | Behavior |
|---|---|
| Non-TTY bare `theforge` | product summary, exit 0 |
| Non-TTY `theforge install` | usage error pointing at `install apply` |
| Interactive fn called headless | `NonInteractive` raised — never blocks |
| `--dry-run` | real plan, zero writes |
| `--yes` | explicit approval for writes |
| `--json` | machine-readable output where supported |

CI pattern:

```bash
theforge install apply --scope project --profile minimal --yes
theforge doctor
```

Interactive input is never required in automation: a missing mandatory
decision fails fast with an actionable error, it does not wait on stdin.
