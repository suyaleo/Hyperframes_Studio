# Research bundle contract

A research bundle is the immutable evidence input to storyboard generation. It is stored as `research/<id>.json` under the configured runtime data directory.

Each bundle records:

- the normalized query, category, collection mode, and UTC collection time;
- provider name, provider kind, status, and result count;
- evidence ID, title, canonical source URL, publisher, publication time, retrieval time, and excerpt;
- optional image candidates with an explicit license status;
- warnings when evidence is sparse or media reuse terms are unknown.

Storyboard cards cite evidence IDs rather than copied titles. Unknown citations from a model response are removed, and a card with no valid citation causes the oMLX response to be rejected. When oMLX is unavailable, the deterministic fallback is labeled in project metadata and the interface; it is never presented as model output.

Remote text is treated as untrusted data. The oMLX prompt separates it from instructions and explicitly rejects commands embedded in sources.
