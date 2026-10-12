# TASKS.md — Phase 1 task tracker

| ID | Task | Status | Commit |
|---|---|---|---|
| P1-00 | Recon & dependency audit | done | |
| P1-01 | Repo baseline, env manifest, docs | done | (P1-01) |
| P1-02 | Upgrade Paddle stack (3.7.0 / 3.3.1) | done | (P1-02) |
| P1-03 | OCR engine wrapper (Latin/numeric) | done | (P1-03) |
| P1-04 | Khmer OCR module (tror-yong-ocr) | done | (P1-04) |
| P1-04b | Khmer dropout guard, script router, AGENTS fix | done | (P1-04b) |
| P1-05 | Layout/table structuring | done | (P1-05) |
| P1-05b | Slim vendored cache, disable formula recognition | done | (P1-05b) |
| P1-06 | Arithmetic validation layer | done | (P1-06) |
| P1-06b | Optional tax/discount rates, drop created_at | done | (P1-06b) |
| P1-07 | Template remark module (replaces removed LLM code) | done | (P1-07) |
| P1-08a | Matching primitives: normalization + tolerance config | done | (P1-08a) |
| P1-08b | Matching engine + MatchResult | done | (P1-08b) |
| P1-08b-fix | Wire currency check via optional currency fields | done | (P1-08b-fix) |
| P1-08c | Match remarks + pipeline integration | done | (P1-08c) |
| P1-09 | Confidence scoring & routing | done | (P1-09) |
| P1-10a | Postgres schema, SQLAlchemy models, Alembic migration | done | (P1-10a) |
| P1-10b | Repository layer + round-trip tests | done | (P1-10b) |
| P1-10c | SQLite → Postgres dev migration | done | (P1-10c) |
| P1-10c-fix | Derive implicit line amounts + header totals in dev migration | done | (P1-10c-fix) |
| P1-11a | Audit log (append-only, input hashing) | done | (P1-11a) |
| P1-11b | Dashboard queries + KPI hooks | done | (P1-11b) |
| P1-12a | Deterministic OCR-to-dataclass extraction layer (apmatch/parse/) | done | (P1-12a) |
| P1-12b | Ruff lint baseline + .dockerignore + dev requirements | done | (P1-12b) |
| P1-12b-fix | Resolve mechanical lint violations, annotate intentional ones | done | (P1-12b-fix) |
| P1-12b-enum | StrEnum migration for Route/CheckCode/etc | pending | |
| P1-12c | Dockerfile + compose app service | done | (P1-12c) |
| P1-12c-fix | Verify non-root + resolve 400-vs-422 (test-harness bug, see D-058) | done | (P1-12c-fix) |
| P1-12d | FastAPI endpoints | done | (P1-12d) |
| P1-12d-fix | Validators handle None fields gracefully, no crashes | done | (P1-12d-fix) |
| P1-12e | Full-stack smoke test | done | (P1-12e) |
| P1-12e-fix | amd64-only smoke marker + CI stub + QEMU docs | done | (P1-12e-fix) |
| P1-13 | Bilingual test corpus + goldens | pending | |
| P1-14 | Delete legacy prototype files + Postgres diagnostic | done | (P1-14) |
| EMB-00 | Deployment parameter lock-in | done | (EMB-00) |
| EMB-01 | Remote deploy skeleton + verify offline | done | (EMB-01) |
| EMB-02 | Vendor MiniLM-L12-v2 model | pending | |
| EMB-03 | apmatch/embeddings/ module | pending | |
| EMB-04 | Embedding tests: determinism, offline, similarity | pending | |
| EMB-05 | Dockerfile update — bake in MiniLM, add sentence-transformers | pending | |
| EMB-06 | Line-item similarity matching in the matching engine | pending | |
| EMB-07 | Similarity matching tests (stub + real) | pending | |
| EMB-08 | Audit log extension — similarity_matches JSONB + Alembic | pending | |
| EMB-09 | Supplier name similarity matching | pending | |
| EMB-10 | Configuration, ARCHITECTURE.md, DECISIONS.md | pending | |
| EMB-11 | Demo fixtures — before/after scenario | pending | |
| EMB-12 | Full-pipeline integration test on server | pending | |
| EMB-12b | Remote deployment runbook + rehearsal | pending | |
| EMB-13 | Demo script (scripts/demo_embedding.sh) | pending | |
| EMB-14 | Demo rehearsal — 3× end-to-end | pending | |

## Deferred

| ID | Task | Status | Commit |
|---|---|---|---|
| CI-1 | Enable GitHub Actions once repo is hosted | pending | |

## Deferred / manual

| ID | Task | Status | Commit |
|---|---|---|---|
| EMB-01b | Remote deploy (human-driven) | done | (EMB-01b) |
| EMB-01e | Server-based test workflow (remote wrappers + dev overlay) | done | (EMB-01e) |
| EMB-01f | Normalizer: lowercase-start mixed OCR suffixes + trailing slash | done | (EMB-01f) |
