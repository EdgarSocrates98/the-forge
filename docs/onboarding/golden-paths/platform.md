# Golden Path — Platform

> Cenário: **"Preciso avaliar a segurança da minha infraestrutura."**
> `platformforge` — análise determinística, offline-first, evidence tiers.

## 1. Instalação

```bash
theforge install platform-forge
platformforge doctor
```

## 2. Seleção de especialista

```bash
theforge ask "avaliar segurança da minha infraestrutura"
```

→ `platform-forge` (postura, secrets, IAM, supply, cost, SLO).

## 3. Análise determinística

```bash
platformforge init        # workspace.yaml
platformforge inspect .
platformforge analyze secrets
platformforge analyze iam
platformforge judge
```

Mesma entrada → mesma saída: a análise é determinística e offline; nenhuma
credencial de nuvem é exigida para a leitura estática.

## 4. Evidências

Findings carregam `rule_id` + facts citados; `planned ≠ observed` —
contradições entre o declarado e o observado aparecem como dois estados,
nunca como um merge otimista. Recusas carregam `PF-*` + `unlock`.

## 5. Recomendações

`platformforge explain` / `recommend` derivam ações dos findings —
sempre ligadas a evidência e regra, nunca a boilerplate genérico.

## 6. Resultado

Postura reproduzível: secrets redigidos na fronteira (nada em claro),
findings auditáveis, itens `unresolved` listados explicitamente em vez de
escondidos.
