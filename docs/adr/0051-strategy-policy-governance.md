# ADR 0051 — StrategyPolicy: a única ponte entre experimentos e routing

- Status: aceito (2026-10-15)

## Contexto

Cycle 4.1 criou `StrategyExperiment/v1` (shadow champion/challenger,
approval obrigatório, sem auto-promoção). Cycle 5 precisa que um experimento
maduro e aprovado possa *influenciar* routing — sem abrir um canal de
auto-promoção.

## Decisão

`StrategyPolicy/v1` (`src/theforge/learning.py`) é o único caminho:

- `promote_experiment` só aceita estado `eligible_for_review` +
  `approval_sha256` real. Experimento inelegível não vira policy, não importa
  quem aprove; `promoted` exige o hash de aprovação (gate do contrato).
- A policy é scoped por `capability` + `surface_fingerprint` exato +
  `task_family`; `prefer` lista o challenger promovido. Métricas são
  recomputadas das observações do challenger — nunca copiadas de prosa.
- `policy_applies` exige match exato de escopo: fora dele a policy é
  neutral, nunca sinal negativo. `valid_until` vencido ou `stale` ⇒ não se
  aplica.
- `refresh_policies` marca `stale` quando a surface medida diverge da atual —
  permanente: policy nunca "des-stala"; nova medição gera nova policy (§117).
- Em `negotiate_all`, a preferência de policy ordena depois de estado,
  dimensões e maturidade — nunca levanta INCOMPATIBLE/UNSUPPORTED.

Correlação não é causalidade: `metrics` registra o que foi medido
(`verified_rate`, `median_*` dos eixos completos), e `limitations` carrega a
ressalva de escopo. Reputação permanece multi-dimensional e scoped
(`ProviderCapabilityPerformance` por provider/capability/surface); não há
score único global (§107-110).

## Consequências

- Routing muda só por evidência promovida + aprovada, auditável por hash.
- Mudança de surface desativa a policy imediatamente — sem herança de
  números.
- Auto-promoção permanece inexistente; estudar `bounded auto-promotion`
  (§106) fica para um ciclo futuro, fora do escopo.
