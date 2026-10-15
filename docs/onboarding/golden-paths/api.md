# Golden Path — API

> Cenário: **"Preciso revisar e evoluir uma API."**
> Rota governada: `analyze → next-step → graph → evidence → brief`.

## 1. Instalação

```bash
theforge install apiforge
```

## 2. Seleção de especialista

```bash
theforge ask "revisar minha API antes da próxima versão"
```

→ `api-forge` (engenharia de API); `forge-doctor-api` cobre diagnóstico
arquitetural offline complementar.

## 3. Contratos e diagnóstico

```bash
cd sua/api
apiforge analyze .
apiforge next-step
```

`analyze` constrói o API-IR com proveniência: rotas, handlers, **contratos**
(OpenAPI/gRPC), auth, deps — sem executar o código. `next-step` propõe a
ação seguinte sobre os fatos; `unresolved` é dito explicitamente.

## 4. Planejamento

Para mudanças não-triviais, o SDD guia:
`discover → intent → contract → architecture → plan → build → verify →
secure → benchmark → ship` — cada fase com gate de evidência.

## 5. Validação

```bash
apiforge verify plan     # planejamento da verificação
forge-doctor-api lab     # corpus de diagnóstico: expected vs observed
```

Findings carregam `fact_id` + regra; recusas expõem código `AF-*` com
campo rejeitado e `unlock` seguro.

## 6. Resultado

Um brief com evidência completa, gaps `unresolved` explícitos e a próxima
ação humana — nada de `DONE` sem verificação independente.
