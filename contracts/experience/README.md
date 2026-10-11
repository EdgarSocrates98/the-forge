# Forge Experience Contracts — v1 (congelados na FASE 0)

Contratos **de produto** compartilhados pelas sete Forjas — o modelo de
estados e envelopes que torna a experiência verificável da mesma forma em
todos os repositórios. São documentos-schema: os repos irmãos os consomem
como alvo de validação (vendored ou por referência), **nunca** como
`import theforge` — a fronteira de pacotes não muda.

Estes contratos são de experiência, não de protocolo de execução: os
contratos de runtime do The Forge continuam em `src/theforge/contracts/`
(`theforge/<Name>/v1`, exportados em `schemas/`).

## O conjunto (§0.3 do programa)

| Schema | Contrato | Cobre |
|---|---|---|
| `forge/ExperienceState/v1` | [experience-state](experience-state.schema.json) | Estado agregado das 5 superfícies (§2) |
| `forge/HostIntegration/v1` | [host-integration](host-integration.schema.json) | Estados §4 + capability matrix §4.1 |
| `forge/InstallationState/v1` | [installation-state](installation-state.schema.json) | Escopos/perfis/componentes §6 |
| `forge/AgentCatalog/v1` | [agent-catalog](agent-catalog.schema.json) | Catálogo agents+skills §11 |
| `forge/TaskInvocation/v1` | [task-invocation](task-invocation.schema.json) | Intenção→rota→evidência §4.2 |
| `forge/DocumentationReview/v1` | [documentation-review](documentation-review.schema.json) | Estados de revisão §12 |
| `forge/ExperienceParity/v1` | [experience-parity](experience-parity.schema.json) | Matriz de paridade §7/§8.1 |

**Reutilizado, não recriado** (§0.3: "reutilizar contratos existentes"):

- `forge/InstallReceipt/v1` — recibo da operação de instalação (já emitido
  pelos instaladores; `InstallationState` é o estado consultável depois).
- `ForgeGraphView/v1` — projeção de grafo publicada pelo Spark Forge AWS
  (`sparkforge_aws_graph_view`); é a forma que os Graph Studios consomem.
- `theforge/AgentSpec/v1`, `theforge/ForgeManifest/v1`,
  `theforge/ExecutionReceipt/v1` — contratos de protocolo já em `schemas/`.

## Regras congeladas

1. **Estado só sobe com evidência.** `ACTIVE`, `EXECUTION_VERIFIED`,
   `SEMANTICALLY_REVIEWED`, `READY` e `SUPPORTED` exigem o campo de
   evidência do schema preenchido com comando+observação.
2. **`UNVERIFIED`/`BLOCKED`/`NOT_APPLICABLE` são estados de verdade** —
   nunca preenchimento provisório, nunca promovidos por conveniência.
3. **Mecanismos de host não são forçados a ser idênticos** (recomendação
   §Primeira): padroniza-se o estado e o resultado; cada host integra pelo
   melhor mecanismo realmente suportado.
4. **Toda recusa carrega `unlock`** — instrução de desbloqueio legível.
5. **Ambiguidade é `ambiguous`**, nunca uma escolha silenciosa.
6. Mudança de contrato = bump de versão (`/v2`), nunca edição in-place.

## Validação

Os schemas são JSON Schema 2020-12. Validar um documento:

```bash
python -c "import json, jsonschema; jsonschema.validate(json.load(open('doc.json')), json.load(open('contracts/experience/host-integration.schema.json')))"
```

`jsonschema` está no grupo dev do the-forge; os irmãos podem vendorar os
schemas que consomem.
