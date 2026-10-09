# Context ROI

Cycle 4.1 adds `ContextROI/v1` and `ContextBudgetRecommendation/v1`.

ROI is comparable only across the same provider, capability and surface
fingerprint, and preferably the same task family.

Measured inputs:

- context bytes;
- context items;
- cited items.

Unknown measurements remain limitations. Citation ratio is utilization, not
causal value.

Budget recommendations require warming/mature history and are advisory only.
They use a conservative floor and never auto-apply.


## Task-family isolation

O escopo por task family é exato. `None` não é wildcard: uma observação sem
task family só é comparada com outras observações também sem task family. Isso evita
que histórico genérico contamine recomendações de uma família especializada.
