# Cycle 2.8 Baseline

This baseline was collected from fresh shallow clones of `main` on 2026-11-10.
The original working directories were not used as implementation baselines
because several were on old release branches or contained audit artifacts.

## Remote `main` heads

| Repository | Initial `main` SHA | Open PRs at audit | Baseline CI evidence |
|---|---|---:|---|
| platform-forge | `9ea66ab3d319a1d95df20fae6af2200d90438257` | 0 | run `42867920506`, PASS |
| the-forge | `b7551be32e6d873f63f106b9538d28aa8f75f0d9` | 0 | run `42864197031`, PASS |
| product-forge | `8ede30c554db305933c6507a96c9754a311d1bfc` | 0 | forge-obsidian publish evidence `42859257773`, PASS |
| api-forge | `076ba0464f6070652259f5c246d3d332e78f782c` | 0 | API CI `42844903701`, PASS |
| spark-forge-aws | `9b5a7e6e77a030efd4a47e60b21bc2bbb786fd54` | 0 | publish evidence `42851531014`, PASS |
| spark-forge-azure | `81c591b4966583280666c9ed9db0adf7b48328e5` | 0 | publish evidence `42851527774`, PASS |
| forge-agent-bridge | `995e59ea9bbaeee3e9a3c920d94294f2f7ddb9ba` | 0 | publish evidence `42851527596`, PASS |
| code-atlas-forge | `c164ea5e2232d2660ad4c9bcf60f63469b604c2c` | 0 | CI/release evidence `42854463221`, PASS |
| forge-lens | `cd9bba04bf19568b7a9116fea99ca09145c24b53` | 0 | publish evidence `42851528746`, PASS |
| forge-portal | `cd43d5e8d53b4d0cb53760ddb854b2fb34153dd9` | 0 | CI evidence `42810286796`, PASS |

## Prior findings classification

| Prior finding | Classification | Evidence in this audit |
|---|---|---|
| Protected context access relied on hash/reference resolution | CONFIRMED | Platform call-graph audit found public `inspect`, `expand`, and `for_role` paths without a trusted authority decision. |
| `delta` could persist an externally supplied capsule without repeating sanitization | CONFIRMED | The pre-change `_persist` path trusted the object shape and hashed its serialized bytes directly. |
| Adapters announced `ObsidianNoteRef` while carrying `content` | CONFIRMED | Four current adapter builders returned body-bearing payloads with the NoteRef schema. |
| Neutral `forge-obsidian` publication | FIXED_ALREADY | Existing successful publication evidence `42859257773`; no duplicate publication performed. |
| API Pages deploy | FIXED_ALREADY / REVALIDATED | Historical `42844903712` failed at artifact lookup; fresh current-main run `42876078863` passed all build, upload, deploy, and health steps. |
| Real cloud/provider federation | REQUIRES_EXTERNAL_VALIDATION | No cloud credentials or production vault authorization were available; fake providers remain clearly separated from this claim. |

The codebase-memory MCP graph query was attempted as required by the workspace
instructions, but its transport was closed. The security call graph was
therefore reconstructed with direct source inspection and `rg`; this is a
tooling limitation, not a claim that graph evidence was obtained.

