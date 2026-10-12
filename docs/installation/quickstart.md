# Quickstart — the-forge

Três comandos:

```bash
git clone <the-forge repo>
cd the-forge
./install.sh      # Windows: .\install.ps1 — account runtime + editable CLI
```

Depois, dentro de qualquer projeto:

```bash
cd ~/meu-projeto
theforge setup
```

O wizard permite escolher instalação global, por projeto ou por workspace,
hosts, perfil econômico/recomendado/full e componentes. Ele mostra o plano
real e pede uma aprovação única para o The Forge e as Forjas especialistas
registradas.

## Verificar

```bash
theforge install status
theforge install doctor
theforge specialists status
theforge portal
```

Detalhes: [account-installation.md](account-installation.md). Problemas? → [troubleshooting.md](troubleshooting.md)
