# Segurança — threat model resumido (ciclos 1 e 2, Wave A)

Modelo de ameaça: repositório analisado malicioso, provider malicioso ou defeituoso e tentativa de escalar trust. Fora do modelo: usuário local mal-intencionado com escrita no próprio home.

| Ameaça | Mitigação | Pendente |
|---|---|---|
| Provider malicioso ou desconhecido | trust (`unverified` fora do routing por padrão, `blocked` nunca executa); repositório não pode se autoconceder trust; providers `unverified` não são executados; subprocess isolado; env por allowlist com filtro de credenciais; policy antes de executar | sandbox de SO ([ADR 0012](adr/0012-os-sandbox-research.md)), assinatura |
| Manifest adulterado ou trocado | id do manifest precisa bater com a entrada; `producer` (id e versão) verificado em describe, health e execute; limites de manifest e rejeição de glob catch-all; todo candidato é descrito de novo antes da decisão final de routing | assinatura de manifest ([ADR 0013](adr/0013-provider-identity.md)) |
| Cache de registry adulterado | cache fora do projeto, no diretório de cache do usuário ([ADR 0009](adr/0009-registry-cache-location.md)); relido com leitura estrita; invalidado se a entrada ou o fingerprint local mudar; providers `unverified` nunca são cacheados; `init` e `registry refresh` removem o legado `.forge/registry` | — (quem escreve no próprio home está fora do modelo) |
| Resultado malicioso ou inconsistente | [integridade do resultado](protocol.md#integridade-do-resultado): IDs únicos, referências resolvidas, caminho de artifact checado sem ser aberto, hashes em hex minúsculo; resultado inválido não é persistido | — |
| Injeção de shell | `argv` em lista, `shell=False` | — |
| Path traversal / symlink | `resolve_inside` no scan e no echo-forge; `..` e symlinks para fora viram `excluded`; caminhos de ContextPack e de artifact checados lexicamente | — |
| Leitura de secrets do workspace | `.env`, `.env.*`, `*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`, `*.pfx`, `*.p12`, `credentials*`, `.npmrc`, `.netrc`, `.pgpass`, `*.token`, `secrets.*` excluídos do ContextPack | detecção por conteúdo; o provider ainda lê o filesystem diretamente (ver limitações) |
| Vazamento de credencial em artefatos | redaction de padrões e chaves sensíveis antes de persistir; stderr do provider truncado e redigido, nunca persistido bruto | — |
| Exaustão de recursos | timeout por op (describe e health 10 s; execute 60 s / 180 s / 600 s em economy / balanced / max); stdout limitado a 8 MB; stderr a 64 KB; kill da árvore de processos em timeout, oversize ou interrupção | limite de CPU/memória |
| Prompt injection via workspace | core não usa LLM | relevante no ciclo com LLM |
| Supply chain do core | zero dependências de runtime (gate de CI); build reprodutível via hatchling | lockfile do dev, assinatura |
| Mutação inesperada | policy `allow/ask/deny` sobre o `operation_class` declarado; artefato `risk` em todo run que chega a um provider; cwd controlado | enforcement real (sandbox) |
| Repositório afrouxando a policy | `.forge/config/policy.toml` só endurece; tentativas de afrouxar são ignoradas com aviso | — |

## Ambiente do provider
O provider recebe só as variáveis abaixo (`ALLOWED_ENV` em `security/env.py`), quando existem no ambiente do pai. Nenhuma outra variável passa.

| Variável | Por que é mantida |
|---|---|
| `PATH` | resolver os executáveis que o provider inicia (python, git, …) |
| `PATHEXT` | Windows: extensões executáveis para resolver comandos no `PATH` |
| `SYSTEMROOT` | Windows: exigida pelo runtime do CPython e pela inicialização do Winsock |
| `SYSTEMDRIVE` | Windows: drive do sistema, usado pelo runtime e na resolução de diretórios temporários |
| `WINDIR` | Windows: diretório do Windows esperado pelas bibliotecas do sistema |
| `COMSPEC` | Windows: interpretador de comandos usado por helpers de subprocess e shell |
| `HOME` | POSIX: `Path.home()` e busca de configuração de ferramentas no processo filho |
| `USERPROFILE` | Windows: `Path.home()` e busca de configuração de ferramentas no processo filho |
| `TEMP` | Windows: diretório temporário para `tempfile` |
| `TMP` | Windows/POSIX: diretório temporário para `tempfile` |
| `TMPDIR` | POSIX: diretório temporário para `tempfile` |
| `LANG` | locale, para decodificação de texto consistente no filho |
| `LC_ALL` | override de locale, para decodificação de texto consistente no filho |
| `PYTHONIOENCODING` | forçada para `utf-8`, para o JSON do protocolo no stdio ser UTF-8 |
| `PYTHONUTF8` | forçada para `1`, para providers Python rodarem em modo UTF-8 |

- `HOME` e `USERPROFILE` continuam porque o Python filho precisa deles (`Path.home()`). Isso não abre acesso novo: o provider já lê o home pelo filesystem (ver limitações).
- Defesa em profundidade: uma segunda passada remove qualquer nome com cara de credencial (`AWS_*`, `TOKEN` como segmento do nome — `GITHUB_TOKEN`, `TF_TOKEN_*` —, `*SECRET*`, `*PASSWORD*`/`*PASSWD*`, `*API_KEY*`/`*APIKEY*`, `*ACCESS_KEY*`/`*ACCESSKEY*`, `*CREDENTIAL*`, `SSH_AUTH_SOCK`, `AZURE_*`, `ARM_*`, `GH_*`, `CLOUDSDK_*`, `ACTIONS_*`, `KUBECONFIG`, `DOCKER_CONFIG`, `NETRC`, `*_PROXY`), mesmo que um dia entre na allowlist por engano, e qualquer valor que contenha uma URL com credenciais (`esquema://usuário@…`). A comparação de nomes ignora maiúsculas.

## Níveis de trust
Trust só é concedido no `providers.toml` do usuário. Detalhes e justificativa em [ADR 0010](adr/0010-policy-model.md).

| Nível | Routing | `local_mutation` | Observação |
|---|---|---|---|
| `builtin` | sim | `allow` | reservado ao core (só o eco embutido) |
| `trusted` | sim | `allow` | |
| `local` | sim | `ask` | roda, mas pede aprovação para mutação local |
| `unverified` | só com `--allow-unverified` | `ask` | padrão; nunca entra no cache |
| `blocked` | nunca | — | filtrado antes da policy; nunca executa |

- Um `providers.toml` de projeto (`.forge/config/providers.toml`) com `trust` acima de `unverified` é rebaixado para `unverified`, com aviso. Sem `--allow-unverified`, o provider aparece como `untrusted` e não é executado (nem `describe`).
- Além da policy, `trusted` e `local` só diferem no desempate quando vários providers declaram a capability pedida com `--capability` (`builtin < trusted < local < unverified`, depois id). A intenção futura é que `trusted` acumule garantias adicionais (por exemplo, identidade forte); se nenhuma se justificar, os dois níveis serão fundidos (ADR 0010).

## Policy e risco
Antes de iniciar o provider, o core decide `allow`, `ask` ou `deny` e grava o artefato `risk` (`RiskAssessment` v1) no run.

- Dimensões: `read_only`, `local_mutation`, `external_read`, `external_mutation` e `destructive` vêm do `operation_class` declarado (só a classe declarada é `yes`); `execution.requires_network = true` força `external_read = yes`. `credentials` e `cross_account` ficam `unknown`.
- Vale a regra mais severa (`allow < ask < deny`) entre as dimensões `yes`. Nenhuma dimensão `yes`, ou regra ausente, resulta em `deny`.
- Regras padrão: `read_only = allow`, `local_mutation.builtin = allow`, `local_mutation.trusted = allow`, `local_mutation.local = ask`, `local_mutation.unverified = ask`, `external_read = ask`, `external_mutation = ask`, `destructive = deny`.
- Configuração: tabela `[rules]` em `policy.toml` no diretório de configuração do usuário (pode afrouxar ou endurecer) e em `.forge/config/policy.toml` (só endurece). A regra aplicada é registrada como `<origem>.<chave>`, com origem `default`, `user` ou `project`.
- `ask` sem aprovação: `refused` com `FORGE-POLICY-APPROVAL-REQUIRED` e `unlock = --approve <capability>`. Com `theforge ask … --approve <capability>`, vira `allow` e o run registra `approved: true`. `deny`: `refused` com `FORGE-POLICY-DENIED`; `--approve` não desbloqueia.
- O `RiskAssessment` sempre registra `source: provider_declaration` e a limitação `operation_class is a provider declaration, not sandbox enforcement`.

## Limitações de isolamento
Não há sandbox. Detalhes e pesquisa por plataforma em [ADR 0012](adr/0012-os-sandbox-research.md).

- **O cwd não é sandbox.** O core escolhe o diretório de trabalho (temporário em describe e health, `.forge/runs/<id>/work` em execute), mas o provider lê e escreve no home e em todo o filesystem com as permissões do usuário, incluindo arquivos de credenciais (`~/.aws`, `~/.ssh`), mesmo sem as variáveis de ambiente.
- **`operation_class` é declaração, não enforcement.** A policy confia no que o provider declara; nada impede um provider de mutar além do declarado.
- **O fingerprint não cobre código importado.** Só o executável e os arquivos do `argv` entram; módulos importados não ([ADR 0013](adr/0013-provider-identity.md)). A revalidação por describe antes do execute compensa em parte. O hash do manifest não prova identidade.
- **O bloqueio de rede dos testes não cobre processos filhos.** Ele atua dentro do processo do pytest; um provider iniciado pelos testes pode acessar a rede.
- **POSIX:** um descendente que sai do grupo de processos (`setsid`, daemonização) escapa do kill da árvore.
- **Windows, modo degradado:** se o Job Object não puder ser criado ou atribuído, o kill usa `taskkill /T /F`, que não alcança um neto órfão cujo pai já terminou. O neto sobrevive, mas a chamada continua limitada (timeout + 2 s de graça + até 5 s de join das pipes).
- **Routing por sinais genéricos:** uma dependência ou keywords genéricas declaradas por **um único** provider confiável ainda podem vencer um provider mais específico, porque distinguir sinal genérico de específico exigiria conhecimento de domínio no core. A mitigação é o trust: só providers configurados pelo usuário roteiam.
