# API Forge Pages Status

The historical failed run `42844903712` was re-opened for diagnosis. Build,
Pages configuration, artifact upload and permissions were successful; the
failure occurred in the deploy step because the run could not resolve the
`github-pages` artifact. Reusing that run produced a duplicate-artifact error,
so it was not treated as a valid fix.

Pages settings were then revalidated: workflow build type, `main` source,
`github-pages` environment policy, and the published URL were present. A fresh
run was dispatched from current `main`:

- workflow: `Publish change-control UI`
- run: `42876078863`
- result: PASS
- evidence: build, configure Pages, upload artifact, deploy artifact, and
  post-deploy health receipt all succeeded.

No code or workflow change was required. The old run is historical evidence,
not the current status.

