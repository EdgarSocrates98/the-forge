# ADR 0062 — catálogo federado de especialistas

- Status: aceito para a onda de baseline (2026-11-02)

## Decisão

O The Forge mantém um catálogo data-driven para todos os especialistas conhecidos, mesmo quando a integração Forge Protocol ainda não existe. O registro carrega identidade, instalação, composição e limitações; não declara capabilities runtime. A promoção para execução exige adapter, handshake e health observados.

## Motivo

Isso permite uma instalação/discovery única para usuários não técnicos sem transformar metadata em falsa disponibilidade. O catálogo pode orientar o próximo passo e o Portal pode mostrar o estado correto (`unadapted`, `degraded`, `ready`) com a mesma verdade da CLI.

## Consequência

Adicionar um especialista exige um JSON estrito, atualização da matriz e testes. Integrar execução exige uma spec posterior com adapter e evidência real; não é permitido resolver esse gap com fallback silencioso.
