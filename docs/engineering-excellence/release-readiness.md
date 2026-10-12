# Release Readiness

## Wave acceptance

- [x] baseline audit and gap matrix
- [x] offline audit command with JSON
- [x] federated descriptor schema
- [x] path-boundary adversarial test
- [x] Rui cp65001 terminal fix
- [x] relevant docs and generated schema
- [ ] specialist descriptors across all adapters
- [ ] cross-Forge benchmark baseline
- [ ] Portal evidence screen backed by API contract
- [ ] CI on every branch and required checks green

## Commands

```text
theforge excellence audit --root <workspace> --json
python -m pytest tests/test_excellence_audit.py tests/test_excellence_contract.py tests/test_ui_experience.py tests/test_ui_screen.py -q
python -m ruff check src tests
```

## Release rule

Do not merge with unavailable/invalid repositories, unreviewed schema drift, failing focused tests, dirty generated artifacts or unverified host writes. Pre-existing Portal screenshot remains outside this change until owner decides.
