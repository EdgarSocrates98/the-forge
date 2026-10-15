# Terraform + Platform Forge

Template de módulo Terraform analisável pelo Platform Forge.

## Instalação
```bash
theforge install platform-forge
cp -r templates/terraform-platform/ minha-infra && cd minha-infra
platformforge init
```

## Testes
```bash
./check.sh   # valida main.tf + platformforge inspect roda
```
