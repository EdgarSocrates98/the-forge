# Ecosystem 2.0 — baseline observada

**Data:** 2026-11-02  
**Fonte:** checkouts locais nesta workspace, manifests, `pyproject.toml`, `package.json`, suites e workflows versionados.

## Resultado executivo

O The Forge já é um control plane local-first com descoberta, knowledge bootstrap, registry, contracts, install kit, context broker, graph federation e portal. A baseline agora inclui os catorze componentes do ecossistema na matriz de compatibilidade.

O estado não é “tudo VERIFIED”: os cinco especialistas adicionados nesta onda possuem metadata de instalação e identidade, porém ainda não possuem adapter Forge Protocol integrado no The Forge. Essa limitação é deliberada e aparece como `UNADAPTED`, nunca como capability inventada.

## Estado por superfície

| Área | Evidência local | Estado |
|---|---|---|
| Control plane | `src/theforge`, contratos, discovery, lifecycle, graph/context e portal | implementado |
| Knowledge/catálogo | `forge-knowledge/*.json`, loader estrito, famílias derivadas de metadata | implementado |
| Matriz de compatibilidade | `ecosystem-compatibility.json`, schema e testes | implementado |
| Adapters existentes | AWS, Azure, API, Platform, Doctor API/Data | implementado/testado |
| Data Sentinel | pacote, CLI e metadata; sem adapter core | parcial |
| Code Atlas | pacote, CLI e metadata; sem adapter core | parcial |
| Forge Lens | pacote, CLI e metadata; sem adapter core | parcial |
| Product Forge | pacote, CLI e metadata; sem adapter core | parcial |
| Agent Bridge | pacote, CLI e metadata; sem adapter core | parcial |
| Portal/CLI | superfície local e comandos existentes | implementado; homologação visual/e2e separada |
| Providers de IA | dependem de login/credenciais externas | bloqueado externamente quando ausentes |

## Limitações da auditoria

- O índice Lumen estava indisponível nesta execução; a descoberta semântica foi substituída por TokenSave e inspeção focalizada. Os grafos TokenSave estavam marcados como stale, portanto não são tratados como prova de frescor.
- Homologação de provider, SMTP, OIDC real e nightly dependem de credenciais/serviços que não podem ser fabricados localmente.
- O diretório `spark-forge-aws/docs/codebase/` já estava sujo antes desta onda e foi preservado.

