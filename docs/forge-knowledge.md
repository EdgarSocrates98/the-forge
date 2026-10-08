# Forge Knowledge Layer

O que a plataforma sabe sobre cada especialista **antes** de ele estar
instalado — e o que ela se recusa a confiar depois.

## O que é

`forge-knowledge/<provider>.json` — um pacote por especialista, validado pelo
contrato `ForgeKnowledge/v1` (`src/theforge/contracts/knowledge.py`),
carregado por `src/theforge/knowledge.py`. Dados autorados, versionados com
o repo, parsing estrito (campo desconhecido falha — §76).

```text
$ theforge knowledge list                  # os seis pacotes
$ theforge knowledge show api-forge        # um pacote (human ou --json)
```

## O que um pacote contém

| Campo | Para quê |
|---|---|
| `id`, `name`, `family`, `summary` | Identidade; `family` alimenta o roteamento por família (`families()`) |
| `repository`, `package`, `binary`, `python`, `adapter` | Onde está, o que instalar, com qual interpretador |
| `install[]` | Métodos reais de instalação (documentados em `real-providers.md`) |
| `verify_install`, `discover_command` | Como provar que instalou; como ler a surface ao vivo |
| `intents`, `appropriate_for`, `inappropriate_for` | Sinais de roteamento de bootstrap — quando usar e quando **não** |
| `composes_with`, `preferred_verifiers`, `independent_verification` | Composição e quem verifica a saída |
| `tested_version`, `tested_surface`, `recorded_at` | O que foi medido, quando — nunca fabricado |
| `environments`, `limitations_note`, `examples` | Onde roda, ressalvas, usos concretos |

## O que ele **não** é

- **Não é verdade de runtime.** `tested_version` é "verificado uma vez, em
  `recorded_at`". Capabilities, saúde e fingerprint vêm do `describe` ao vivo
  — o pacote só acelera o caminho até a descoberta ([ADR 0052](adr/0052-forge-knowledge-layer.md)).
- **Não é capability.** Skills e pacotes dizem *como usar*; o manifest diz
  *o que existe* ([ADR 0053](adr/0053-skill-vs-capability.md)).
- **Não se auto-atualiza.** Versão nova = plano novo + aprovação nova (§58).

## Adicionar um especialista

1. Crie `forge-knowledge/<id>.json` a partir de evidência real (repo,
   pyproject, docs de instalação).
2. `id` == nome do arquivo; o loader rejeita divergência.
3. Rode `pytest tests/test_forge_knowledge.py` e `audit_assets.py` — skills
   com `[freshness]` apontando para ele são checadas contra `tested_version`.
