# Uninstall — the-forge

```bash
theforge uninstall            # remove só arquivos gerenciados
theforge uninstall --purge    # + remove o estado local (.forge/install/)
```

O ledger SHA-256 decide ownership: arquivos que você criou ou modificou
depois da instalação ficam no lugar (reportados como `kept`). Diretórios
que esvaziam são podados; os seus permanecem.
