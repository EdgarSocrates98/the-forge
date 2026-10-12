# Capability Parity Matrix

Estado não significa qualidade absoluta. Significa evidência encontrada na baseline.

Legenda: `strong` evidência local ampla; `partial` evidência incompleta; `unknown` sem contrato federado; `planned` próxima onda.

| Capability | The Forge | API Forge | AWS | Azure | Platform | Doctor API | Doctor Data | Portal |
|---|---|---|---|---|---|---|---|---|
| routing / specialization | strong | partial | strong | strong | partial | partial | partial | partial |
| capability registry | strong | strong | strong | partial | strong | partial | partial | unknown |
| contracts / schemas | strong | strong | partial | partial | partial | strong | partial | partial |
| context / knowledge | strong | strong | partial | strong | strong | partial | strong | partial |
| SDD / task planning | partial | strong | partial | partial | partial | unknown | unknown | unknown |
| TDD / evals / benchmarks | partial | strong | strong | strong | strong | strong | strong | partial |
| economy / token budget | strong | strong | strong | strong | strong | partial | partial | partial |
| diagnosis / architecture fitness | strong | partial | partial | partial | strong | strong | strong | partial |
| human / agent invocation split | planned | partial | partial | partial | partial | unknown | unknown | partial |
| explainability / receipts | partial | partial | partial | partial | partial | strong | strong | partial |
| install / portability | strong | partial | partial | partial | partial | unknown | unknown | strong |
| visual status / graph | partial | partial | partial | partial | strong | partial | strong | strong |
| deterministic federation audit | planned | planned | planned | planned | planned | planned | planned | planned |

## Interpretation

- `strong` não autoriza copiar componente. Reusar contrato e adapter local.
- `partial` exige evidência adicional antes de promessa de paridade.
- `unknown` exige investigação; não vira `missing` sem teste ou contrato.
- `planned` pertence a ondas seguintes, não baseline.
