# ADR 0064 — segurança operacional e limites de evidência agentic

- Status: aceito para a resolução Goldfish (2026-11-06)

## Decisão

O ecossistema reutiliza o executor, a policy, o task id e os contratos de
receipt existentes. Esta decisão não cria um runtime, ledger, transporte ou
fonte de lifecycle novos. Todo agente especializado opera dentro de quatro
limites explícitos:

1. **Orçamento observável.** O plano declara limites de `steps`,
   `tool_calls`, `wall_time_ms`, `bytes_read` e `bytes_written`. Custo de
   provedor só pode ser declarado quando houver medição; caso contrário o
   valor é `unknown`. O executor aplica hard stop e retorna `BLOCKED` ou
   `UNKNOWN`, nunca uma estimativa apresentada como custo medido.
2. **Trust boundaries.** Intento e aprovação do usuário, manifestos e skills,
   paths/artefatos, comandos, credenciais e output de provider são domínios
   distintos. Manifesto e skill são declarações não confiáveis; não concedem
   trust nem execução. Paths são resolvidos dentro do escopo autorizado e
   symlinks, comandos e segredos passam pelas guardas existentes. Credenciais
   não chegam ao ambiente do provider.
3. **Telemetria honesta.** Cada execução local produz a receipt mínima já
   prevista, com `trace_id`, task id, estado e artefatos. Quando o provider não
   entrega spans ou custo, a receipt usa `partial_trace` ou
   `telemetry_unavailable`; ausência de telemetria nunca é convertida em
   `PASS`.
4. **Verificação sem gate de cold start.** Histórico de verificação é sinal de
   ranking e risco. Ele não bloqueia um especialista novo sem histórico; o
   hard gate continua sendo capability, estado, trust, disponibilidade e
   health observados.

Planos aprovados continuam bounded, expiráveis e consumíveis uma vez. Retry,
cancelamento e reconexão reutilizam task id/receipt e os estados canônicos da
tarefa; não podem criar uma segunda verdade de lifecycle.

## Alternativas rejeitadas

1. Colocar custo ou health inferidos no manifesto: declaração não é medição e
   produziria confiança falsa.
2. Exigir histórico positivo para todo routing: impediria especialistas novos
   e confundiria ausência de histórico com falha.
3. Tratar trace ausente como sucesso: esconderia lacunas de auditoria e
   provider variability.
4. Criar um ledger de orçamento/telemetria paralelo: duplicaria a autoridade
   de task, receipt e policy já existentes.

## Riscos e evidência de aceitação

| Risco | Mitigação | Evidência mínima |
|---|---|---|
| Manifesto, skill ou output malicioso | declaração separada de trust; capability observada e gates existentes | ADR 0063; conformance de roster e routing |
| Symlink, path amplo ou segredo em comando | escopo de path, redaction e credencial fora do env | invariantes de `AGENTS.md`; receipt redigida |
| Custo não medido ou execução longa | unidades explícitas, teto e hard stop; `unknown` sem medição | plano/receipt com limites e estado de bloqueio |
| Provider sem trace ou com telemetria parcial | `partial_trace`/`telemetry_unavailable` | contrato de receipt e campo de limitação |
| Histórico insuficiente | ranking advisory e cold start permitido | decisão de routing; nenhum gate baseado só em histórico |
| Retry duplicar trabalho | task id, receipt e plano consumível uma vez | lifecycle Portal e ADR 0059 |
| Fixture ou catálogo envelhecido | hash/fingerprint, frescor e `BLOCKED`/`UNKNOWN` | contrato Spark `docs/golden-paths/spark-diagnostic.json` |

## Consequências

- O Portal e o catálogo podem explicar por que uma ação está bloqueada ou
  desconhecida sem fabricar uma conclusão.
- Orçamento, confiança e telemetria permanecem evidência operacional, não
  novas dimensões de autoridade do manifesto.
- A implementação é compatível com os providers atuais e com o golden path
  Spark local; execução live e verificação independente continuam exigindo
  receipts próprias.
