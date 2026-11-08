# Unresolved risks

1. The Forge's installed provider registry contains stale/unavailable provider
   entries. The invalid `FORGE_DOCTOR_API_VENV` user variable was repaired to
   the existing installed venv and `theforge doctor` is now healthy.
2. Data Sentinel, Code Atlas, Forge Lens and Agent Bridge are discoverable but
   not uniformly promoted to routable The Forge adapters.
3. The Agent Bridge provider matrix has no universally authenticated provider;
   Devin is detected authenticated, but no session was opened in this cycle.
4. Portal visual and CLI compatibility are strong, but live service federation
   still needs a real PortalApi backend matrix.
5. Spark/AWS live execution remains blocked by expired AWS SSO and is outside
   this local API lab. No cloud mutation was attempted.
6. The cycle does not create `api-sentinel-forge`; doing so before adapter,
   ownership and evidence gates pass would duplicate existing responsibilities.
