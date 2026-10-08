---
name: forge-platform
description: When and how to use platform-forge: platform engineering and repo posture (GHA workflows, k8s, GitOps, IaC, observability, SRE, service catalog, secrets scanning). Load for CI/CD/platform-estate analysis; NOT for app code, Spark or API contracts.
---

# forge-platform

<background_information>
Operational guide to `platform-forge` — nine `analyze_*` seams plus a native `capability_manifest`: `iac.*`, `k8s`, `secrets.scan`, `gha.analyze`, `gitops`, `catalog`, `platform.manifest`. `theforge knowledge show platform-forge` is the bootstrap source of truth.
</background_information>

<instructions>
## Recognize it when the task mentions

GitHub Actions / CI/CD pipelines · Kubernetes manifests/Helm · GitOps (Argo/Flux) drift · Terraform/IaC posture · observability/SLO/OTel · service catalog/Backstage · golden paths / DX / IDP · secrets scanning of a repo tree.

## Boundaries — do NOT route here

- API contract design → `api-forge` (compose: api-forge → platform-forge for design+deploy).
- Spark → spark family. Self-verification → independent doctor.

## Operate

1. `theforge knowledge show platform-forge` — venv-pip recipe (`platformforge>=0.1,<0.2`, Python ≥3.10).
2. `secrets.scan` sees only the *staged* tree: the core excludes secret-bearing inputs (`.env` etc., `reason: secret`) before the specialist runs — `ok`/`0 facts` means the boundary held, not that the repo is clean. This limit is declared on the capability itself.
3. Dogfooding-proven on this repo: `gha.analyze` produces per-workflow facts with sha256-verified evidence.

## Limits

Staging boundary above is intentional. Refusals preserve `PF-*` codes with `unlock` instructions.
</instructions>
