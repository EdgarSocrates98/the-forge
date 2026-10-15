# Golden Path — Multi-Forge

> Cenário: **"Tenho uma aplicação com API, infraestrutura e pipelines."**
> Descoberta e integração entre especialistas.

## 1. Instalação

```bash
theforge setup   # perfil recommended/full instala as Forjas registradas
```

## 2. Descoberta

```bash
theforge specialists list
theforge capabilities
theforge graph
```

Você vê o que cada Forja **declara** e o que foi **observado** — o grafo
não mostra capacidade inventada.

## 3. Integração entre especialistas

```bash
theforge ask "revisar API + segurança da infra + performance do pipeline"
```

Intenções multi-domínio retornam `ambiguous` com as candidatas — o
roteador decompõe, mas você confirma. Para execução coordenada:

```bash
theforge plan "..."    # plano multi-provider; nós verificados reutilizam
theforge task "..."    # execução real via argv do especialista
```

## 4. Diagnóstico e evidências

Cada especialista produz seus receipts — `theforge explain`/`replay`
re-conta a execução com os artefatos reais, e `theforge lab collect`
agrega os benchmarks federados:

```bash
theforge lab collect --mode A
theforge lab gate --baseline docs/programs/ecosystem-2026/benchmarks/results-2026-10-15-A.jsonl
```

## 5. Resultado

Uma composição auditável: cada especialista respondeu no seu domínio com
evidência, o coordenador não inventou respostas fora do declarado, e os
vereditos finais (incluindo `skipped`/`ambiguous`) estão nos receipts.
