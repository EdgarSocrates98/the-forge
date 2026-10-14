# Certificação final do ecossistema The Forge

**Data da revisão:** 2026-10-14  
**Programa:** `prompt_evo_auditabilidade.md`  
**Estado:** `CERTIFICATION_BLOCKED`

## 1. Resumo executivo

Esta revisão produziu baseline reproduzível, validação de contratos, handshakes
MCP locais, cenários determinísticos e matriz de instaladores. O caminho PR do
Spark Forge AWS foi reduzido para smoke focado; a auditoria completa continua
disponível em workflow manual/nightly.

A certificação integral não é emitida. Permanecem bloqueios de ambiente e de
evidência: Linux real, hosts externos, runner Portal cross-forge reproduzível,
deep scan e findings de dependências. Ausência de execução não é interpretada
como sucesso.

## 2. Baseline das nove mains

| Projeto | SHA auditado | Independência | Contratos | Integração | E2E | Status |
|---|---|---|---|---|---|---|
| The Forge | `c0b1e8571c80a30f3e8c388e499fe002759a1667` | CONDITIONAL | PASS | CONDITIONAL | CONDITIONAL | BLOCKED |
| Forge CLI | `f893bb0308f2c4016e024d7e21a2e9e79f09c64a` | CONDITIONAL | NOT_TESTED | CONDITIONAL | NOT_TESTED | BLOCKED |
| Forge Portal | `88015f233bab105c0cbae173fbbcddc6665bb346` | CONDITIONAL | CONDITIONAL | BLOCKED | BLOCKED | BLOCKED |
| API Forge | `bccf56eb4c03feefe5af69058af1c9704e276fd3` | PASS local | PASS | CONDITIONAL | PASS local | CONDITIONAL |
| Spark Forge AWS | `6a728debb881fcf4765407f33e4824096ec55af2` | PASS local | PASS | CONDITIONAL | CONDITIONAL | BLOCKED |
| Spark Forge Azure | `d3e37697ee740f511445938b707828cec62fb12f` | PASS local | PASS | CONDITIONAL | PASS local | CONDITIONAL |
| Platform Forge | `d34b90c435634b13d618af7e4271ab04beb0db6e` | PASS local | PASS | CONDITIONAL | PASS local | CONDITIONAL |
| Forge Doctor Data | `66ce9ca5464f8cc46199166fcea47cce9f25999e` | PASS local | PASS | CONDITIONAL | PASS local | CONDITIONAL |
| Forge Doctor API | `1bf561ec08988582b1817cef3d219a50d4c66b78` | PASS local | PASS | CONDITIONAL | PASS local | CONDITIONAL |

Fonte: `audit/baseline/`. Os SHAs acima não devem ser misturados com SHAs de
branches de correção.

## 3. Ambiente e matriz de evidência

Ambiente principal: Windows local, Python 3.14.6, PowerShell 5.1/7, Git Bash,
Node/npm e GitHub Actions Linux/Windows quando disponíveis. Linux Bash real,
CUA visual e hosts externos não estavam disponíveis.

| Fase | Estado | Evidência |
|---|---|---|
| H0 baseline | PASS | `audit/baseline/*.json` |
| H1 independência | CONDITIONAL | `installer-matrix.json`: 21 PASS, 7 BLOCKED Linux |
| H2 contratos | CONDITIONAL | `contract-validation.json`, `mcp-handshake.json`: 6/6 MCP local |
| H3 CLI/Portal | CONDITIONAL | instaladores PASS; Portal cross-forge BLOCKED |
| H4 hosts/MCP/agentes | BLOCKED | MCP local PASS; Claude/Devin/Copilot não verificados |
| H5 workflows multi-Forge | CONDITIONAL | `evidence-index.json`: 19/19 cenários locais PASS; SHAs de runtime divergentes em parte |
| H6 segurança/observabilidade | CONDITIONAL | findings Snyk não fechados; deep scan BLOCKED |
| H7 regressão/certificação | CONDITIONAL | AWS smoke `38497876506` PASS; full dispatch `38500376956` em execução no momento da revisão |

## 4. Capacidades, contratos e independência

Contratos dos nove repositórios foram validados. O handshake MCP local executou
`initialize`, `tools/list` e chamada read-only em seis servidores, totalizando
388 ferramentas catalogadas. Isso prova protocolo local; não prova que cada
host externo consegue iniciar a configuração instalada.

Os instaladores foram exercitados em PowerShell 5.1, PowerShell 7 e Git Bash.
Os sete casos Linux permanecem `BLOCKED` por ausência de distribuição Linux.
The Forge não foi introduzido como dependência de runtime dos especialistas.

## 5. Instalação, lifecycle e cenários E2E

Dry-runs, descoberta, help, análises locais, scans determinísticos e bootstrap
foram executados. O índice atual registra 19/19 cenários locais `PASS`. Esses
resultados usam checkouts/runtime locais e não substituem prova da mesma versão
de `origin/main` quando o SHA diverge.

Não há evidência atual suficiente para declarar os gates P0 de remoção do
orquestrador, ciclo completo de instalação/atualização/rollback/desinstalação,
Portal cross-forge e hosts externos como homologados.

## 6. Segurança, resiliência e observabilidade

- Nenhuma alteração em AWS/Azure, produção, release ou infraestrutura real foi executada.
- Logs e artefatos passaram por redaction básica e validação JSON.
- Snyk foi executado, mas findings de dependências continuam `UNVERIFIED_FOR_RELEASE`.
- Deep scan permanece `BLOCKED` por ausência do permission profile exigido.
- Métricas desconhecidas não foram preenchidas como valores fictícios.

## 7. Correções implementadas

- AWS: `graph build`, atualização de Portal/bundle e CI PR rápido com smoke focado.
- AWS: full pytest/matriz/wheels/audit/OTel mantidos em push, nightly e dispatch.
- The Forge: baseline H0 atualizado, evidências frescas registradas e estados
  conflitantes normalizados sem promover evidência histórica.
- Nenhum teste foi removido, nenhum threshold foi reduzido e nenhum histórico
  Git/PR/Actions foi apagado.

## 8. PRs e regressão

- [spark-forge-aws#164](https://github.com/EdgarSocrates98/spark-forge-aws/pull/164)
- [the-forge#61](https://github.com/EdgarSocrates98/the-forge/pull/61)

PRs de correções anteriores já mergeados permanecem referenciados no relatório
de auditoria. CI AWS smoke `38497876506` e CI The Forge `38498576625` terminaram
verdes. Full AWS dispatch `38500376956` deve ser anexado somente após conclusão.

## 9. Testes não executados e riscos residuais

Não executados ou não comprovados: Linux Bash real, Firefox/WebKit quando
indisponíveis, CUA visual, Claude/Devin/Copilot, runner Portal cross-forge
reproduzível, deep scan, fechamento dos findings Snyk e todos os cenários E2E
P0 contra SHAs H0 estritos.

Riscos residuais: regressão específica de host, divergência de runtime entre
baseline e checkout local, vulnerabilidades sem correção publicada e cobertura
visual/Portal incompleta.

## 10. Recomendação de release

Não liberar como homologado integralmente. Manter `CERTIFICATION_BLOCKED`,
fechar os gates listados em `audit/reports/prompt-evo-auditabilidade.md` e
regenerar este documento após evidência autoritativa nova. O smoke PR AWS pode
ser obrigatório para feedback rápido; full matrix/nightly deve continuar como
gate de regressão periódica, sem ser mascarado por smoke verde.
