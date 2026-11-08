# Bridge parity report

Product Forge now runs `scripts/check_bridge_parity.py` in a dedicated CI job. The
job checks out `EdgarSocrates98/forge-agent-bridge@main`, records the canonical
revision and compares the complete `.py`/`.json` inventory and bytes against the
vendored `src/forge_agent_bridge` tree. It fails on missing, extra or drifted files.

Local receipt: `status=VERIFIED`, canonical revision
`1c560542b99c4cb1892e29b9376211341286cf67`, embedded revision
`a73c36f4107d48df7d60f8969764c003ed7c0192`.
