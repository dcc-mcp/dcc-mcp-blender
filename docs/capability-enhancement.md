# Evidence-led Blender capability enhancement

## Upstream reference and boundaries

[Blender Lab's MCP server](https://www.blender.org/lab/mcp-server/) is a
Blender-published project, distinct from community Blender MCP servers.
Its [versioned source](https://projects.blender.org/lab/blender_mcp/src/commit/4309a39646e644261624bfcd2bca669b343b7621)
provides progressive API documentation lookup and explicitly warns about
unguarded Python execution. Documentation lookup is useful; permissive
execution is not a replacement for typed operations or authorization.

Our first batch adds runtime-bound RNA property discovery, not an automatic
wrapper around every Blender API. Core continues to own tool registration,
execution, result envelopes and transport. Blender owns RNA interpretation,
main-thread access and host-specific postconditions. No new protocol is
required by other adapters for these additive tools.

## Query before authoring, read back after authoring

Load `blender-rna` only when current-host type/property knowledge is needed:

1. `search_rna_types(query="modifier")` finds public runtime type identifiers.
2. `describe_rna_type(type_name="SolidifyModifier", query="thickness")`
   returns property types, bounds, static enums and read-only flags.
3. After an independently authorized typed operation,
   `get_modifier_values(object_name="Panel", modifier_name="Solidify",
   properties=["thickness"])` reads exact values.

Check each property's `status`. An unsupported pointer, collection or runtime
callback is **not** successful verification. These queries never evaluate
expressions, follow data paths or invoke operators. Discovering an RNA member
does not promise that a corresponding mutation tool exists, nor that an
operator's context preconditions are satisfied. See the
[official operator context guidance](https://docs.blender.org/api/5.2/info_gotchas_operators.html).

Results identify the actual Blender version and schema
`dcc-mcp-blender.rna-query.v1`. Follow `next_offset` for further pages and
inspect enum truncation/status flags; static enums are not a complete list of
context-dependent dynamic choices. Responses have a 32 KiB JSON budget, so
pages can return fewer rows than requested. `returned` and `next_offset` reflect
the actual page. Text, arrays and enums also have explicit bounds.

## Regression rubric

| Task | Baseline gap | Acceptance evidence |
| --- | --- | --- |
| Discover current modifier parameters | No dedicated typed RNA query | Search pages; current-host Solidify bounds and Subsurf enum values |
| Verify modifier postconditions | Modifier list reports identity/visibility only | Solidify scalar and Mirror array readback; missing and unsupported fields explicit |
| Inspect without authoring | Generic scripting can mutate | Objects, selection, active object, frame, transforms and modifiers unchanged by queries |
| Refuse unsafe selectors | Generic introspection accepts broader targets | Expressions, private names and unknown RNA types fail without execution |

Unit tests cover hostile and oversized values. Real-host tests live in
`tests/e2e/test_rna_query_e2e.py`; they use separate synthetic fixtures rather
than modifying an artist's scene. These are contract/host regressions, not
proof of improved model success rates or complete Blender API coverage.

## Following batches

- Fix validation false positives for empty shader graphs and missing images.
- Enforce object/cache scope and truly non-mutating simulation dry runs.
- Query evaluated geometry separately from graph structure or base mesh counts.
- Extend host-version regressions before claiming modern nodes, hair or animation
  support. Legacy particle tools do not establish Maya nHair/Bifrost parity.
- Evaluate representative tasks with saved artifacts and independent readback.
  For interchange, assess units, axes, material links, images, LOD and animation
  separately; a successful import is not full-fidelity acceptance.
