# Portal API Operations

O Portal foi evoluído no PR #88, integrado no commit
`324b6287facd45bb4573577410303ca1e0d8600a`.

## Fluxo entregue

```text
Service explorer → contrato importado → operações → New investigation
```

A tela usa o backend Product Forge real via `PfApi` e não contém fixtures de
produção. Mostra saúde, contratos, operações, parâmetros e navega para o fluxo
canônico de tarefa. Os estados são explícitos: `LOADING`, `AVAILABLE`, `EMPTY`,
`UNAVAILABLE` e `UNVERIFIED`.

## UX e acessibilidade

- entrada pelo dashboard, busca e rota lazy `/api-operations`;
- PT-BR/EN com paridade verificada;
- teclado, focus ring, layout desktop/mobile e dark/light mode;
- backend ausente vira erro/`UNAVAILABLE`, nunca lista vazia fabricada;
- build sem warning de orçamento do componente após a compactação do estilo.

## Evidência

```text
npm test -- --watch=false      55 files, 592 tests passed
python -m pytest e2e -q        45 passed, 3 skipped
visual probe                   no serious/critical axe, no focus failures
visual audit                   224 captures, horizontal overflow 0
CI                              PASS, incluindo Browser E2E e vendor parity
```

Uma sessão contra Product Forge remoto autenticado é **NOT_RUN** neste ambiente;
o comportamento de indisponibilidade é coberto por teste de componente.
