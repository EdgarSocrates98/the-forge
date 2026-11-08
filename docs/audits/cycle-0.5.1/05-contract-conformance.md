# Contract conformance

| contract area | result | note |
|---|---|---|
| `forge/PortalApi/1` | PASSED | envelope e erros estruturados preservados |
| Agent Bridge events | PASSED | unknown/error/replay/redaction cobertos |
| provider manifests | PASSED | roster federado validado |
| router eligibility | PASSED | seleção determinística e razões observáveis |
| receipts | PASSED | hash/integridade verificados no lab |
| external provider contract | NOT_RUN | sem sessão autenticada disponível |

Não foi criado contrato paralelo para API Operations. O Portal usa `PfApi`, os
modelos `PfProduct`, `PfApiSpec` e `PfProductHealth`, e encaminha execução ao
fluxo governado `/tasks?new=1`.

Os testes negativos continuam exigindo erro específico para provider ausente,
manifest inválido, capability ambígua, timeout, saída inválida, credencial
ausente e receipt incompleto.
