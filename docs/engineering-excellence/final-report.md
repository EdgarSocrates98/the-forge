# Engineering Excellence — relatório final

Data: 2026-10-12  
Branch federada: `codex/evo-grill-2026-10-12`  
Especificação: `factory/specs/active/lf-0005-engineering-excellence.md`  
Prompt: `E:\projetos\FORJAS\prompt_evo_grill.md` no workspace de execução

## A. Sumário executivo

O programa foi executado em ondas pequenas, com evidência local, contratos preservados e commits separados por responsabilidade. O resultado principal é uma camada de auditoria federada no The Forge, contrato de capability versionado, matriz de paridade, catálogo declarativo de repositórios, evidência de experiência, hardening de caminhos, resiliência do Rui e paridade de onboarding nos CLIs especialistas.

O roteamento existente continua autoridade para execução. A auditoria não instala, não executa especialistas e não substitui registries locais. Custos desconhecidos permanecem `unknown`; ausência de runtime aparece como indisponibilidade, nunca como sucesso inventado.

## B. Paridade e decisões

- `KEEP`: registry, adapters, roteamento especializado, contratos locais, Doctors e portal existentes.
- `REFINE`: auditoria offline, contrato federado, documentação de contexto, gates de release e evidência de experiência.
- `ADAPT`: práticas de grill, scope, implement-spec, code review, retrospectives e contexto sob demanda para os limites reais do ecossistema.
- `REJECT`: copiar skills em massa, criar superagente, obrigar novo manifesto, alegar suporte uniforme entre hosts ou estimar economia sem medição.
- `INCONCLUSIVE`: benchmark comparativo de tokens/custo real e execução com runtimes especialistas instalados neste host.

Referências inspecionadas: [Skills for Real Engineers](https://github.com/mattpocock/skills), `SCOPE.md`, `grill-with-docs`, `implement-spec` e `code-review`.

## C. Repositórios

| Repositório | Base | Final | Mudança nesta onda | Validação | Estado |
|---|---|---|---|---|---|
| the-forge | `06b7d1c` | `8c68a09` | auditoria, contrato, catálogo, Rui Windows, evidência e docs | 463 testes direcionados + E2E AWS + Ruff | READY WITH LIMITATIONS |
| api-forge | `4ed0360` | `20a2b74` | kit/wizard Rui alinhados | 15 pass, 1 skip | READY WITH LIMITATIONS |
| spark-forge-aws | `b554143` | `bb2198b` | kit/wizard Rui alinhados | 14 pass; 2 falhas `DEGRADED` preexistentes na suite ampla | READY WITH LIMITATIONS |
| spark-forge-azure | `59e25c0` | `bd85416` | kit/wizard Rui alinhados | 14 pass | READY WITH LIMITATIONS |
| platform-forge | `17a6f45` | `797fc13` | kit/wizard Rui alinhados | 14 pass | READY WITH LIMITATIONS |
| forge-doctor-api | `c1dc3c3` | `7ed4279` | kit/wizard Rui alinhados | 14 pass | READY WITH LIMITATIONS |
| forge-doctor-data | `4975032` | `e85595a` | kit/wizard Rui alinhados | 14 pass | READY WITH LIMITATIONS |
| forge-portal | `f1c0611` | `18a776e` | readiness UX documentado; nenhum código alterado nesta onda | screenshot local preexistente preservado | READY WITH LIMITATIONS |

O arquivo `forge-portal/e2e/artifacts/02-language-toggle.png` já estava modificado antes desta execução e não foi incluído em commit.

## D. Evidência técnica

- `theforge excellence audit --root ... --json` executa offline, produz estado, commit, capabilities, evidência, confiança, custo e próxima ação.
- Catálogo `docs/engineering-excellence/repositories.json` remove identidade de especialistas do núcleo Python; novos repositórios entram por dado versionado.
- `FederatedCapabilityDescriptor/v1` separa invocação humana, agentic e host; schema gerado e seed de fuzz adicionados.
- Auditoria recusa caminho externo, symlink escape e marcador externo; falhas retornam exit code 3.
- `cp65001` é reconhecido como terminal Unicode; fallback ASCII e não-TTY continuam preservados.
- Resolver de especialistas usa caminho retornado por `shutil.which`; launcher `.cmd`/`.exe` funciona de forma estável fora da shell que fez discovery.
- Kit, i18n e wizard mantêm contrato de paridade entre The Forge e CLIs especialistas; somente arquivos divergentes foram sincronizados.
- Reality/experience snapshots marcam runtimes especialistas ausentes neste host como `missing`.

## E. Benchmarks e economia

Não foi inventada economia. O host não forneceu medição confiável de tokens/custo para comparação A/B, e os runtimes especialistas não estão instalados nas variáveis esperadas. O benchmark está classificado `INCONCLUSIVE`; o catálogo e os relatórios preservam campo `unknown` e próximos passos para execução em ambiente equipado.

## F. Compatibilidade

- Offline: auditoria e documentação funcionam sem rede.
- Windows: resolver de launcher testado contra `.cmd` real; Rui reconhece encoding Windows UTF-8.
- TTY/non-TTY: contrato existente preservado; fallback ASCII mantido.
- Hosts: suporte é reportado por evidência existente; nenhum host sem validação foi declarado suportado.
- Instalação/router/portal: mecanismos já existentes foram preservados; esta onda não criou fluxo paralelo nem obrigou instalação de todas as Forjas.

## G. Retrospectiva

Problemas observados: identidade de repos hardcoded na auditoria, launcher Windows detectado mas não executável por nome cru, drift de Rui entre CLIs, lacunas de documentação e snapshots sem runtime real. Correções foram pequenas, testáveis e commitadas por onda. O próximo ciclo deve coletar baseline com especialistas instalados, executar benchmark comparativo e publicar compatibilidade efetiva por host.

## H. Gaps residuais

1. Instalar runtimes reais dos seis especialistas para validar integração executável completa.
2. Resolver as duas falhas AWS existentes que retornam `DEGRADED` na suite ampla.
3. Executar benchmark A/B repetido com métricas de contexto, custo, duração, retries e qualidade.
4. Completar validação visual automatizada do Portal em CI; screenshot local preexistente segue fora do patch.
5. Evoluir descritores federados dos adapters sem forçar migração dos manifests locais.

## I. Recomendação de release

**READY WITH LIMITATIONS.**

Critérios essenciais de código, contratos, auditoria, portabilidade local, paridade Rui e documentação estão atendidos. Integração federada completa e benchmark econômico ficam limitados pela ausência de runtimes/telemetria neste host e devem permanecer explícitos no PR e no CI.
