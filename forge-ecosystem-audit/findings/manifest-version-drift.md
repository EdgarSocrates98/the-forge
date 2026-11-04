# Finding: manifest-version-drift (CONFIRMED → VERIFIED_FIXED)

- Classificação: CONFIRMED → VERIFIED_FIXED
- Ciclo: 01 (correções estruturais e contratos)
- Severidade: alta (bloqueia "Gate A — Integridade")

## Evidência
- `product-forge/forge.json` dizia `0.1.0` enquanto `src/product_forge/__init__.py` = `0.2.0`.
- `forge-agent-bridge/forge.json` dizia `0.1.0` enquanto `pyproject.toml` = `0.2.0`.
- `product-forge` vendora `src/forge_agent_bridge/` com `__version__ = 0.1.0`;
  código byte-idêntico ao bridge@0.2.0 (`diff -rq -x __pycache__` → só `__init__.py` difere).

## Correção aplicada
- `forge.json` → `0.2.0` em ambos os repos.
- `product-forge/src/forge_agent_bridge/__init__.py` → `0.2.0` (vendored bridge).
- Testes de coerência manifesto↔pacote adicionados nos dois repos
  (`tests/test_manifest_version.py`).

## Aberto (decisão de produto, plano §2.3)
- Mecanismo reproduzível de sync do Bridge vendored vs. dependência explícita.
- `capability_version`/`schema_version`/`protocol_version` ainda não existem
  separados em `forge.json`.
