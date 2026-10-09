# ADR 0052 — Forge Knowledge Layer: metadado de bootstrap, nunca verdade de runtime

- Status: aceito (2026-10-08)

## Contexto

Antes de um especialista estar instalado, a plataforma precisa responder:
para que ele serve, como reconhecer uma tarefa dele, como instalá-lo, como
verificar a instalação e quem verifica a saída dele (prompt agentic §5-7).
Essa informação não existe em lugar nenhum executável — vive em docs, nos
repos dos especialistas e na cabeça de quem operou.

Ao mesmo tempo, conhecimento estático sobre providers é exatamente o tipo de
dado que apodrece: versões mudam, surfaces mudam, comandos de instalação
mudam. Se o core passasse a confiar nele em runtime, teríamos reintroduzido
conhecimento de domínio no control plane — a fronteira que o projeto inteiro
protege.

## Decisão

`forge-knowledge/<provider>.json` + contrato `ForgeKnowledge/v1`
(`src/theforge/contracts/knowledge.py`, loader `src/theforge/knowledge.py`):

- Um pacote por especialista, com `id == nome do arquivo` (o carregador
  rejeita divergência — como os AgentSpec).
- Conteúdo: repositório, pacote/binário, `python`, `adapter`, `install[]`
  (métodos reais documentados em `docs/real-providers.md`), `verify_install`,
  `discover_command`, `preferred_verifiers`, `family`, `intents`,
  `appropriate_for`/`inappropriate_for`, `composes_with`,
  `independent_verification`, `tested_version` e `tested_surface` quando
  medidos.
- **Bootstrap, não verdade**: `tested_version`/`tested_surface` são "o que
  foi verificado uma vez", com `recorded_at`; capabilities, saúde e surface
  ao vivo vêm sempre do `describe`/registry (§7). Onde não há medição, o
  campo fica ausente — nunca fabricado.
- **Parsing estrito**: pacotes são dados autorados do core, versionados com
  o repo — `from_dict(..., strict=True)`. Um campo contrabandeado
  (`trust_level`, `priority_multiplier`) falha a validação, não é tolerado
  como forward compatibility (§76).
- `families()` deriva o roteamento por família do metadado — não há
  abstração nova de "família" no core.
- Skills `forge-*` referenciam pacotes via `[freshness]`; a auditoria falha
  quando `tested_version` diverge do pacote — skill stale é defeito
  detectável, não surpresa (§52, §78).

## Consequências

- Onboarding e roteamento de bootstrap têm fonte versionada e auditável.
- Conhecimento estático não pode vazar para runtime: quem decide é sempre a
  descoberta ao vivo; o pacote só acelera o caminho até ela.
- Adicionar um especialista é escrever um JSON + adapter — sem tocar o core.
