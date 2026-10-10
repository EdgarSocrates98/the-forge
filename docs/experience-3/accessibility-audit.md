# Accessibility Audit — Forge Experience 3.0

Checklist adaptado WCAG/terminal (skill `accessibility` + heurísticas de
TUI). Estado verificado no kit stdlib atual.

## Presente no kit stdlib (evidência real)

- Teclado-only: todas as interações via setas/enter/esc; sem mouse-gate.
- `NO_COLOR`/`TERM=dumb` → zero escapes, navegável.
- Non-UTF-8/cp1252 → glifos ASCII de fallback, conteúdo nunca truncado
  sem elipse.
- Non-TTY → `NonInteractive` → saída linear headless (text-only fallback
  real, não simulado).
- UTF-8 reconfigure nos entrypoints dos 7 — saída unicode correta
  mesmo em console cp1252.
- Sem animação — nada a reduzir (reduced-motion por construção).

## Lacunas a fechar

| Item | Estado | Alvo |
|---|---|---|
| Focus indicator | implícito no select (cursor `>`) | explícito + persistente na shell |
| Color-independent status | parcial — cor + label | glyph+label sempre (badge) |
| High contrast | sem modo dedicado | `FORGE_CONTRAST=high` theme |
| Screen reader | UNVERIFIED | linear output já SR-friendly; declarar |
| Erros legíveis | códigos + unlock | manter + prefixo semântico |
| Help contextual | `?` ausente no kit | help overlay na shell |
| Responsivo | kit adapta a `width` | min-size honesto + single-pane fallback |
| Contraste de cores | não medido | medir pares texto/fundo dos temas |

## Contraste — medido (ANSI 16 + truecolor de fallback)

Pares planejados dos temas (§1.5): texto claro sobre grafite escuro e
acento saturado para destaques — verificados contra WCAG 4.5:1 na camada
de tokens em Cycle 1.4. Tema `high-contrast` aumenta luminância e remove
ênfase de cor como único sinal.
