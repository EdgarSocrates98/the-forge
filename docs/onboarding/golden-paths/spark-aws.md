# Golden Path — Spark AWS

> Cenário: **"Tenho um job Glue lento."**
> Ponta a ponta com comandos reais do `sparkforge-aws` instalado.

## 1. Instalação

```bash
theforge install spark-forge-aws   # ou dentro do `theforge setup`
sparkforge-aws doctor              # confirma o ambiente
```

## 2. Seleção de especialista

```bash
theforge ask "meu job Glue está lento"
```

O roteador resolve para `spark-forge-aws` (domínio Glue/PySpark). Se a
intenção fosse ambígua ("otimizar meu pipeline"), o retorno seria
`ambiguous` com as candidatas — nunca um chute.

## 3. Diagnóstico

```bash
cd seu/repo-de-jobs
sparkforge-aws analyze .
sparkforge-aws case show
sparkforge-aws next-step
```

`analyze` extrai **facts** determinísticos do código (read/write paths,
formatos, partições, joins, skew potencial); `next-step` propõe a próxima
ação sobre os fatos — a mesma entrada produz sempre a mesma saída.

## 4. Análise de evidências

Cada finding cita `rule_id` + evidência de código. `not_applicable`
significa "a regra não se aplica", não "falhou calado". Facts são
observações sem juízo; findings sempre referenciam ≥1 fact.

## 5. Recomendações

`sparkforge-aws next-step` encadeia as ações sugeridas — partição, formato,
skew, broadcast — sempre justificadas por um finding, nunca por
preferência genérica.

## 6. Testes

```bash
sparkforge-aws lab
```

O lab do próprio engine roda o corpus determinístico e reporta
precisão/cobertura medida — cenários `skipped` são recursos não suportados,
reportados honestamente.

## 7. Resultado

Um diagnóstico reproduzível: refazer `analyze` no mesmo commit produz os
mesmos facts e findings. O resultado é um conjunto de recomendações com
evidência — a decisão final (aplicar ou não) continua humana.
