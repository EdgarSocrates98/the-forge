# Segurança — threat model resumido (ciclo 1)

| Ameaça | Mitigação no ciclo 1 | Pendente |
|---|---|---|
| Provider malicioso ou desconhecido | trust (`unverified` fora do routing por padrão, `blocked` nunca executa); repositório não pode se autoconceder trust; providers `unverified` não são executados; subprocess isolado; env por allowlist | sandbox de SO, assinatura |
| Manifest adulterado | id do manifest precisa bater com a entrada; cache com sha256 verificado na leitura | assinatura de manifest |
| Cache de registry adulterado (`.forge/registry/` pode vir no repo) | providers `unverified` nunca são cacheados nem lidos do cache; leitura revalida id e protocolo | um cache forjado ainda pode falsificar capabilities de um provider já confiável (sem execução de código); mover o cache para diretório do usuário num ciclo futuro |
| Injeção de shell | `argv` em lista, `shell=False` | — |
| Path traversal / symlink | `resolve_inside` no scan e no echo-forge; `..` e symlinks para fora viram `excluded` | — |
| Leitura de secrets do workspace | `.env`, `.env.*`, `*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`, `*.pfx`, `*.p12`, `credentials*`, `.npmrc`, `.netrc`, `.pgpass`, `*.token`, `secrets.*` excluídos do ContextPack | detecção por conteúdo |
| Vazamento de credencial em artefatos | redaction de padrões e chaves sensíveis antes de persistir; stderr do provider redigido | — |
| Exaustão de recursos | timeout por op (describe e health 10 s; execute 60 s / 180 s / 600 s em economy / balanced / max); stdout limitado a 8 MB; stderr a 64 KB | limite de CPU/memória |
| Prompt injection via workspace | core não usa LLM no ciclo 1 | relevante no ciclo com LLM |
| Supply chain do core | zero dependências de runtime; build reprodutível via hatchling | lockfile do dev, assinatura |
| Mutação inesperada | `operation_class` declarado; cwd isolado por run | policy allow/ask/deny (ciclo futuro) |
