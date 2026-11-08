# Bridge parity report

Product Forge now runs `scripts/check_bridge_parity.py` in a dedicated CI job. The
job checks out `EdgarSocrates98/forge-agent-bridge@main`, records the canonical
revision and compares the complete `.py`/`.json` inventory and bytes against the
vendored `src/forge_agent_bridge` tree. It fails on missing, extra or drifted files.

Local receipt: `status=VERIFIED`, canonical revision
`1b8ac82df64cdd53e7ff17324d325e82d8dbaff9`. The embedded tree is byte-equal
to that canonical source; its checkout revision is intentionally not used as a
parity claim because it belongs to the Product Forge distribution commit.
