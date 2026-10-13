# ADR 0053 — Skill não é capability: separação de superfícies

- Status: aceito (2026-10-08)

## Contexto

O prompt agentic (§8-16) pede 15 skills `forge-*` de ecossistema e de
especialista. Surge o risco óbvio: uma skill que descreve "o que api-forge
faz" pode facilmente virar uma segunda declaração de capabilities — duas
fontes de verdade, uma das quais o runtime ignora.

## Decisão

Skills e capabilities são superfícies diferentes com donos diferentes:

- **Capability** é declarada pelo provider no manifest (adapter →
  `describe`), negociada por `capability_graph`/`negotiate` e decidida por
  routing determinístico. É a única superfície que o core executa.
- **Skill** é orientação para o host (Claude/Codex/Devin): quando carregar,
  quais verbos existem, quais limites respeitar, para onde delegar. Vive em
  Markdown, é renderizada por host e **nunca é lida pelo runtime**.
- Uma skill especialista declara `[freshness] specialists = [...]` — aponta
  para o pacote de conhecimento, nunca enumera capabilities. A frase
  "capabilities ao vivo vêm do `describe`" está em todas elas.
- Auditoria garante: skill sem `description` não carrega sob demanda;
  freshness divergente do pacote falha; referência `$forge-x`/`/forge-x`
  para algo que não existe falha.

## Consequências

- Não há "segunda lista de capabilities" para dessincronizar: a skill diz
  *como usar*, o manifest diz *o que existe*.
- Skill pode ser verbosa sobre workflow (instalação, verificação, composição)
  porque não compete com o manifest — complementa.
- Se o especialista muda de surface, quem apodrece é o `tested_version` da
  skill — e a auditoria acusa, em vez de a skill fingir que ainda vale.
