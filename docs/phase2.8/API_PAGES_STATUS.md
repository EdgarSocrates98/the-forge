# API Forge Pages Status

The historical failed run `42844903712` was re-opened for diagnosis. Build,
Pages configuration, artifact upload and permissions were successful; the
failure occurred in the deploy step because the run could not resolve the
`github-pages` artifact. Reusing that run produced a duplicate-artifact error,
so it was not treated as a valid fix.

Pages settings were then revalidated: workflow build type, `main` source,
`github-pages` environment policy, and the published URL were present. The
initial baseline-main revalidation was `42876078863` (PASS). After the API
adapter merge, the first final-main run `42890977559` again failed at artifact
resolution, so a fresh run was dispatched from the exact final `main` SHA
`c2b95826cfa71c68d8e164c50e89a2eeced0fb2c`:

- workflow: `Publish change-control UI`
- run: `42895987092`
- result: PASS
- evidence: build, configure Pages, upload artifact, deploy artifact, and
  post-deploy health receipt all succeeded.

No code or workflow change was required. The artifact-resolution failure is
retained as a transient external Pages observation; the fresh final-main run
is the acceptance evidence.

