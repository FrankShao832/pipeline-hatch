# Pipeline Vocabulary

One page of agreed terms, following the convention used by large North American
studios (and by ShotGrid / ftrack / rez). The point of the page is that two
words are **not** interchangeable, and every tool in this pipeline must use them
the same way.

> **Core rule:** the **department** is the data axis, the **DCC** is the runtime
> axis. Departments own data; applications open data.

---

## Terms

| Term | Meaning | Where it lives | Example values |
|:--|:--|:--|:--|
| **department** | Organisational owner of the work. Owns approvals, permissions, farm pools, delivery specs and version numbering. | Path segment, DB column, permission scope, farm pool, `DEPARTMENT` / `PIPELINE_DEPARTMENT` | `model` `rig` `anim` `layout` `fx` `lighting` `comp` |
| **step** | Planning-level stage in the tracking system (ShotGrid/ftrack "Step"). Drives scheduling and status roll-up; usually 1:1 with a department but is its own registry. | Tracking DB (shot/asset status), review scheduling | `Modeling` `Animation` `FX` `Comp` |
| **task** | The smallest unit of *assigned work*: one (step × shot/asset) instance, carrying assignee + status. | Tracking DB only | `comp/cy_city_0010` assigned to an artist |
| **dcc** | The application. A runtime choice: which program opens the work. | Launch target, file extensions, command flags, environment packages, provenance metadata. `DCC` / `PIPELINE_DCC` | `maya` `houdini` `nuke` `katana` |
| **publish type** | Kind of artifact produced. Orthogonal to both axes above. | Publish path segment, publish metadata | `script` `cache` `geo` `render` `review` |
| **provenance** | Which dcc + version + environment produced a file, recorded so it can be reproduced later. | Metadata only | `maya 2026.1, rez context …` |

### Why department sits above dcc

1. **Cardinality** — department → dcc is N:1 (several departments share one app);
   dcc → department is 1:N.
2. **Derivability** — a default dcc can be derived from a department; a
   department cannot be derived from a dcc (seeing `nuke` does not tell you
   comp, roto or paint).
3. **Ownership** — a department has a supervisor who signs off; an application
   has no owner.
4. **Stability** — department vocabulary has been stable for decades; the dcc
   behind a department changes (lighting moving from Houdini to Katana is a
   normal event).
5. **Integration points** — farm pools, approvals, ACLs and delivery specs are
   all organised by department.

## Rules

1. **Department is the data key.** A DCC name never appears as a directory
   segment that carries data identity.
2. **DCC may nest inside a department** when one department uses several apps:
   `fx/houdini/`, `comp/nuke/`. Department goes on the outside.
3. **Version counters are scoped to (department, publish type)** — never to a
   dcc, never to a shot alone.
4. **Identity never embeds either token.** An asset is `<shot>_<name>`; the
   department is a field, not part of the name. Renaming on reallocation must
   not be necessary.
5. **DCC travels as provenance**, so any published file can be traced back to
   the application and version that produced it.
6. **`task` is not a synonym for `department`.** UI labels, class names, env
   vars and directory names use `department`.

## Path templates

```
work      <project_root>/<show>/<seq>/<shot>/<department>[/<dcc>]/<filename>
publish   <publish_root>/<show>/<seq>/<shot>/<department>/<publish_type>/v###/<filename>
shot usd  <publish_root>/<show>/<seq>/<shot>/<shot>.usda
asset usd <publish_root>/<show>/assets/<name>/v###/<name>_v###.usd
```

## Transitional: legacy DCC-named trees

App-named trees (`<shot>/nuke`) used to exist. They were migrated on
2026-10-25 — 43 moves across every project on disk, applied by
`plan/migrate_disk_vocab.py`, with a reversible manifest in
`plan/disk_vocab_migration_20261025.tsv`. The launcher still resolves a
DCC-named folder as the last fallback so an unmigrated tree cannot break, but
new trees never use that shape.

Resolution order in the launcher (`resolve_workdir`):

1. `<shot>/<department>/<dcc>` — department running several apps
2. `<shot>/<department>` — normal shape
3. `<shot>/<dcc>` — legacy fallback only

## Alignment status (2026-10-25)

| Tool | Status |
|:--|:--|
| **Pipeline Hatch** | Aligned — `DepartmentSelectorWidget` (starts on *Select your department*, no implicit department), department-first workdir, DCC as launch target only, project trees migrated to department folders |
| **Pipeline Publisher** | Pending — `path_builder.path_for_publish()` names its segment `department` but receives a dcc token on disk; version counters therefore collide across departments |
| **Asset Manager** | Pending — `assets.asset_type` + `assets.dcc_type` in parallel, no `department` column; asset names embed the department |
| **Stage Weaver** | Already compliant at path level — keys on asset + version only, uses a DCC purely to launch |
