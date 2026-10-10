# Agentic actions

Node investigation → bounded context for a specialist:

1. capture node id (provider-namespaced), incident edges, evidence;
2. build the minimum useful subgraph (neighbors within depth, capped);
3. preserve provenance + epistemic state verbatim;
4. budget: over budget returns a named refusal, never a silent
   truncation;
5. graph labels/attributes are *data*: serialized as JSON, never spliced
   into instructions — prompt-injection surface is closed by
   construction;
6. routing/delegation go through the existing governed mechanisms
   (`task run`); the execution record links back to the node id.
