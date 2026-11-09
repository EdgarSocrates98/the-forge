# Release Readiness

## Wave acceptance

- [x] baseline audit and gap matrix
- [x] offline audit command with JSON
- [x] federated descriptor schema
- [x] path-boundary adversarial test
- [x] Rui cp65001 terminal fix
- [x] relevant docs and generated schema
- [x] specialist descriptors across all adapters — manifests e adapters homologados em `docs/phase2/SPECIALIST_ADAPTERS.md`
- [ ] cross-Forge benchmark baseline
- [x] Portal evidence screen backed by API contract — fluxo governado e receipts cobertos por `docs/phase2/FINAL_ACCEPTANCE.md`
- [ ] CI on every branch and required checks green

## Commands

```text
theforge excellence audit --root <workspace> --json
python -m pytest tests/test_excellence_audit.py tests/test_excellence_contract.py tests/test_ui_experience.py tests/test_ui_screen.py -q
python -m ruff check src tests
```

## Release rule

Do not merge with unavailable/invalid repositories, unreviewed schema drift, failing focused tests, dirty generated artifacts or unverified host writes. Pre-existing Portal screenshot remains outside this change until owner decides.
