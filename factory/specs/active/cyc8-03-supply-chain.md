---
id: cyc8-03
title: supply-chain-security
status: active
created: 2026-10-15
owner: the-forge
scope: ecosystem
cycle: 8
wave: 1
priority: p0
risk: high
agent: codex
source: prompt_evo_cycles.md §8.8
verification:
  - python scripts/check_gates.py --pytest
---

# Supply chain security dos artefatos

## Outcome

Artefatos de release verificáveis: builds reproduzíveis, hashes SHA-256, SBOM, checagem de dependências e licenças, proveniência de build, assinatura quando viável e publicação por CI com permissões mínimas.

## Grill gate

- Problema observado: nenhum artefato do ecossistema tem proveniência/integridade verificável hoje.
- Usuário afetado: quem instala Forjas e precisa confiar no artefato; auditor de segurança.
- Falha concreta: artefato adulterado ou dependency confusion não seriam detectados.
- Decisão: aplicar §8.8 quando apropriado — reproducible build, SHA-256, SBOM, verificação de deps/licenças, proveniência, assinatura quando viável, política de atualização de deps, verificação de vulnerabilidades, proteção contra dependency confusion, CI com permissões mínimas.
- Fora de escopo: assinatura obrigatória onde não viável; telemetria; bloquear contribuição externa.
- Critério de parada: consumidor consegue verificar hash+SBOM de cada artefato publicado; pipeline publica com permissões mínimas.

## Acceptance

- Hashes SHA-256 publicados por artefato e verificáveis localmente.
- SBOM gerado por pacote (Python wheels e pacote npm do CLI, bundle do Portal).
- Verificação de vulnerabilidades e licenças em CI; política de atualização de dependências documentada.
- Proteção contra dependency confusion (escopo/registry fixado, sem fallback silencioso).
- Documento `security.md` do programa atualizado com evidências.

## Constraints

- Não introduzir dependência de runtime nova no core the-forge para suportar verificação.
- Ferramentas de SBOM/scan entram como dev/CI, não como requisito do usuário final.

## Rejected

- Tratar scan de vulnerabilidades como gate bloqueante sem política de severidade definida (registrar política primeiro).

## Pending

- ⚠ Assinatura de artefatos: viável com qual mecanismo (sigstore/gpg)? Registrar decisão.
- ⚠ Registry alvo (PyPI/npm) define o formato de proveniência — depende de cyc8-02.
