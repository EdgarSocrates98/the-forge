# Ecosystem 2.0 — arquitetura de integração

The Forge permanece o único control plane. Os especialistas são processos independentes, descritos por manifests e observados por `describe`/`health`. O fluxo canônico é:

```text
knowledge bootstrap → discovery → registry → protocol handshake → health
       → routing proposal → approval/plan token → execute → evidence → Lens
```

O Portal e o CLI são superfícies sobre esses serviços; não criam um segundo orquestrador. Os cinco especialistas sem adapter ficam no catálogo para instalação/discovery, mas o routing deve recusar execução e explicar a ausência da superfície Forge Protocol.

