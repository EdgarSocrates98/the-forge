# Ontologia compartilhada

Vocabulário alinhado entre The Forge, os Doctors e os especialistas. Cada
membro mantém seus modelos nativos; esta é a semântica comum que a tradução
dos adapters deve preservar. Contratos formais: `schemas/`;
transporte: `protocol.md`.

## Conceitos

| Conceito | Definição | Dono |
|---|---|---|
| **Evidence** | Fato observável com fonte (`ref`), atômico e auditável. Em The Forge: `Evidence{id, source, kind, summary, data, derived_from}`. Nos Doctors: `forge_doctor_*.Evidence` nativo — estruturalmente mais rico (confidence, file:line). | quem observa |
| **Finding** | Evidência interpretada com severidade. Forge: `Finding{code, severity, summary, evidence}`. Doctors: finding nativo com `confidence` + `unknowns` obrigatórios quando `UNKNOWN`. | quem julga |
| **Capability** | `namespace.action` declarado no manifest do provider. A única unidade de roteamento do core — o core nunca inventa nem decompõe capabilities alheias. | provider declara, core roteia |
| **Unknown** | Incerteza explícita, nunca zero implícito. Aparece como `limitations[]` (conhecido-ausente) e `unresolved`/`not_applicable` (métricas de economia). Nos Doctors: `UnknownFact` + `Confidence.UNKNOWN` exige `unknowns`. | quem declara |
| **Decision** | `DecisionRecord` — veredito composto com alternativas rejeitadas e razões. No debate core, proposers carregam seu veredito de domínio como evidence `id="decision"`; o referee compõe o cross-domain. | o nível que compõe |
| **Artifact** | Arquivo persistido com hash (`sha256`) e tipo declarado. `artifacts[]` no resultado referencia `work/` do provider; `PlanRefs` referencia artifacts do plano (`plan.json`, `decision.json`, `economy.json`…). | quem produz |
| **Graph** | Três níveis, ownership explícito — ver `architecture.md` §Federação. Nunca merged; referências cross-level via `Xref`. | Forge / Doctors / especialistas |
| **Receipt** | Prova de execução auditável. `ExecutionReceipt` (core) por run; `ProviderReceipt` aninhado aponta o receipt nativo do especialista (`ref` + `sha256`); `ProviderEconomyReceipt` para métricas. | cada nível o seu |

## Epistemic vocabulary

O eixo epistêmico do Forge é **como o fato foi obtido** — não a confiança
do emissor nele:

| Forge `kind` | Significado | Uso típico |
|---|---|---|
| `confirmed` | Verificado por meio independente neste run | saída do verifier op |
| `observed` | Lido diretamente de uma fonte (scan, coleção, leitura) | findings dos Doctors |
| `inferred` | Derivado deterministicamente de observações | junções do grafo |
| `proposed` | Hipótese/estimativa, sujeita a debate ou verify | plans, estimates |
| `unresolved` | Declarado como não-decidido — nunca preenchido por chute | unknowns explícitos |

### Mapeamento por provider

| Fonte nativa | → Forge `kind` | Preservação |
|---|---|---|
| Doctor Data `evidence_kind="observed"`/`source_record` | `observed` | `confidence` nativa vai para `limitations` |
| Doctor Data `evidence_kind="derived"` | `inferred` | idem |
| Doctor API `Evidence` + `Confidence` | `observed` (scan) ou `inferred` (derived) | `native confidence: {high,medium,low,unknown}` preservado verbatim em `limitations`; `UNKNOWN` nunca vira finding sem `unknowns` |
| Spark Forge AWS `Fact` (extracted) | `observed` | severity/contagem de facts preservadas |
| Especialista `proposal`/`estimate`/`debate` | `proposed` | — |
| Verifier op | `confirmed` | — |

Severidade Forge `low|medium|high|critical` é lossless de ida e volta com
o vocabulário dos Doctors (`LOW|MEDIUM|HIGH|CRITICAL` → minúsculas).

## Regra de tradução lossless

Quando um campo nativo não tem equivalente exato no contrato do protocolo:

1. **Preservar verbatim em `limitations`** — ex.: `native confidence: low`,
   `confidence: UNKNOWN`. Nunca achatar (`low`→`medium`), nunca descartar.
2. **Nunca preencher por inferência** — campo ausente na fonte é ausência
   no protocolo, não default fabricado. `unresolved`/`not_applicable` são
   os valores honestos, não `0`/strings vazias.
3. **O tradutor declara a perda** — se a tradução aproxima (ex.: mapear
   `CONFIRMED` nativo para `observed` porque o Forge não verificou), a
   aproximação aparece em `limitations` do item traduzido.

Referência: `adapters/doctordata/.../translate.py`,
`adapters/doctorapi/.../translate.py` — ambos já implementam (1)–(3);
`test_contracts.py` e os testes de adapter cobrem os casos.

## Proveniência ponta a ponta

Cadeia preservada em cada run, sem achatar níveis:

```
Doctor finding ──► handoff item (origin={plan_run,node,run_id,provider})
    ──► specialist evidence (data="origin:<sha>" + derived_from)
    ──► verify op (VerifyRequest carrega o handoff)
    ──► synthesis (seções citam node ids de origem)
```

Cada elo é um artefato hash-addressable; o próximo nível cita o `sha256`
do anterior em vez de copiar o conteúdo. Detalhes em `protocol.md`
§Proveniência e `architecture.md` §Federação.
