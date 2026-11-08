# Installation and portability

O ciclo preservou o caminho de instalação sem flags para os projetos do catálogo.
A matriz local confirmou 14/14 participantes com `home`, `tui` e `wizard` em
streams TTY, instalação visual e instalação portátil.

```text
uv run python scripts/cli_install_matrix.py --check    14/14 PASS
uv run python scripts/cli_runtime_smoke.py             28/28 PASS
uv run --with pywinpty --no-cache python scripts/cli_tty_smoke.py --seconds 8
                                                        14/14 PASS
uv run --with pywinpty --no-cache python scripts/cli_tty_cancel_smoke.py --seconds 3
                                                        14/14 PASS
```

Os scripts preservam `install.sh`, `install.ps1` e `install.windows.sh` onde
aplicável. O smoke de cancelamento validou `q`, Escape/Clack e `q+Enter` sem
aplicar mutação acidental.
