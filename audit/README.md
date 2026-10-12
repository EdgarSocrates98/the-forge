# Forge ecosystem audit

Auditoria evidence-first do ecossistema Forge.

Este diretório é infraestrutura de validação e documentação. Não é importado
por nenhuma Forge e não participa do runtime de produção.

## Baseline

O baseline é coletado contra `origin/main` de cada repositório, sem trocar o
checkout ativo:

```powershell
python audit/tooling/collect_baseline.py --workspace-root .. --ref origin/main
```

Saídas:

- `baseline/repositories.json`: SHA, branch, runtime, instalação e comandos.
- `baseline/versions.json`: versões declaradas e tags remotas.
- `baseline/capabilities.json`: contratos, entry points, testes e workflows.
- `baseline/dependencies.json`: dependências declaradas e dependências Forge.
- `baseline/workflows.json`: workflows disponíveis por repositório.

Cada registro contém `provenance`, com comando, arquivo/ref e timestamp da
coleta. Ausência de evidência permanece explícita; o relatório não converte
documentação em `PASS`.
