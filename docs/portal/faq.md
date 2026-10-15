# FAQ do ecossistema

**O que é o The Forge?**
O control plane do ecossistema — decide WHO/WHEN/HOW. O WHAT (domínio)
pertence às Forjas especialistas. Veja `docs/onboarding/README.md`.

**Preciso de credenciais de nuvem para usar?**
Não para análise estática — os especialistas são offline-first e
determinísticos. Mutação em nuvem fica fora do núcleo, atrás de adapters e
policy gates explícitos.

**O roteador pode escolher o especialista errado?**
O routing é determinístico: ambiguidade retorna `ambiguous` com as
candidatas — nunca um chute. Sem LLM no núcleo.

**Onde ficam as evidências de uma execução?**
Receipts sob `.forge/` no workspace; benchmarks federados em
`docs/programs/ecosystem-2026/benchmarks/`. `theforge explain <run>` re-conta
qualquer execução.

**O que `unresolved`/`not_available`/`skipped` significam?**
Estados honestos: a medição não existe ou não se aplica. Nunca viram `pass`
nem `0`.

**Posso contribuir com uma Forja nova?**
Sim — o modelo de contribuição exige validação de manifesto, capabilities,
permissões e proveniência antes de confiar (cyc10-03, §10.9). Forjas
externas não são confiáveis por padrão.
