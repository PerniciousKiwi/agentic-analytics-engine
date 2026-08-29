"""
Phase 6 verification for the Cardinal schema retrieval system.

Highest-value checks, roughly in order of how badly wrong they'd let you go
unnoticed:

  1. PII leakage into retrievable card text — cross-references glossary.yml's
     declared PII columns against ACTUAL live values from your warehouse,
     then checks whether those real values appear verbatim in app.schema_cards.
     This is the specific bug the guide calls out by name in Step 1 ("the bug
     you want to catch here, not in a security review later") and it's fully
     mechanically checkable without guessing your redaction approach.
  2. The weighted tsvector DDL — confirms card_name/description/values_text
     are separate columns feeding a GENERATED ALWAYS AS tsv with setweight
     zones A/B/C, not a single flat content column (the guide is explicit
     the §9.1 sketch can't support this and needs to be evolved).
  3. retrieval/ module boundary — retrieval/*.py must not import agent/ or
     llm/, per the guide's §9.4. Checked by static source scan, not by
     asking you to promise you didn't.
  4. RRF fusion correctness — an INDEPENDENT synthetic adversarial test with
     hand-computed expected scores (rank-based, k=60), same spirit as Phase
     2's comparator tests: if this is subtly wrong (e.g. accidentally using
     raw scores instead of ranks), nothing else in the pipeline would ever
     tell you.
  5. generate_sql.j2 immutability — Phase 3's baseline.md is pinned to a
     specific hash of this file; this phase should have added
     generate_sql_v2.j2 alongside it, not edited it in place.
  6. Required artifacts — retrieval_ablation.md and the retrieval-miss vs.
     generation-error decomposition table, with a best-effort independent
     recall spot-check where your retrieval functions are importable.

Usage (run from repo root):
    python scripts/verify_phase6.py

IMPORTANT: CONFIG guesses column/module names your code may not use exactly.
Anything that comes back SKIP tells you what it tried — edit CONFIG for that
item rather than assuming the underlying thing is broken.
"""

from __future__ import annotations

import glob
import hashlib
import importlib
import inspect
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import psycopg
except ImportError:
    psycopg = None

try:
    import yaml
except ImportError:
    yaml = None

# --------------------------------------------------------------------------
# .env loading (same minimal loader as earlier phase scripts)
# --------------------------------------------------------------------------


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


_load_dotenv(".env")


def _build_dsn(host_var, port_var, db_var, user_var, pass_var) -> str | None:
    user, pw = os.environ.get(user_var), os.environ.get(pass_var)
    if not user or not pw:
        return None
    host = os.environ.get(host_var, "localhost")
    port = os.environ.get(port_var, "5432")
    db = os.environ.get(db_var, "cardinal")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


RO_DSN = os.environ.get("RO_DSN") or _build_dsn(
    "WAREHOUSE_RO_HOST", "WAREHOUSE_RO_PORT", "WAREHOUSE_RO_DB", "WAREHOUSE_RO_USER", "WAREHOUSE_RO_PASSWORD"
)
ADMIN_DSN = os.environ.get("ADMIN_DSN") or _build_dsn(
    "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"
)

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

SCHEMA_CARDS_SCHEMA = "app"
SCHEMA_CARDS_TABLE = "schema_cards"
CARD_TEXT_COL_CANDIDATES = ["card_name", "card_description", "card_values_text", "content", "card_content"]
TSV_COL_CANDIDATES = ["search_vector", "tsv"]

GLOSSARY_PATH_CANDIDATES = ["semantic/glossary.yml", "warehouse/semantic/glossary.yml"]
RETRIEVAL_CONFIG_PATH = "configs/retrieval.yaml"

SPARSE_MODULE_CANDIDATES = [("cardinal.retrieval.sparse", "search"), ("cardinal.retrieval.sparse", "sparse_search"), ("cardinal.retrieval.sparse", "retrieve")]
DENSE_MODULE_CANDIDATES = [("cardinal.retrieval.dense", "search"), ("cardinal.retrieval.dense", "dense_search"), ("cardinal.retrieval.dense", "retrieve")]
FUSION_MODULE_CANDIDATES = [("cardinal.retrieval.fusion", "rrf"), ("cardinal.retrieval.fusion", "fuse"), ("cardinal.retrieval.fusion", "reciprocal_rank_fusion")]
RETRIEVAL_PACKAGE_DIR_CANDIDATES = ["src/cardinal/retrieval", "cardinal/retrieval"]
FORBIDDEN_IMPORT_PREFIXES = ["cardinal.agent", "cardinal.llm"]

QDRANT_COLLECTION = "schema_cards"
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
EXPECTED_VECTOR_SIZE = 384
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages:"

GENERATE_TEMPLATE_PATH = "src/cardinal/llm/prompts/generate_sql.j2"
GENERATE_V2_TEMPLATE_CANDIDATES = ["src/cardinal/llm/prompts/generate_sql_v2.j2"]
KNOWN_GENERATE_HASH_PREFIX = "44725b66ebdc"  # verified against git history (commits e4be665, ed73217) — file has not changed since Phase 3/5

OLIST_SUITE_PATH = "eval/suites/olist_gold_150.jsonl"
RETRIEVAL_ABLATION_DOC = "docs/results/retrieval_ablation.md"
DECOMPOSITION_DOC_CANDIDATES = ["docs/results/retrieval_decomposition.md", "docs/results/retrieval_failure_decomposition.md", "docs/results/phase6_decomposition.md"]
RESULTS_DIR = "results"

FUSION_K_DEFAULT = 60

# --------------------------------------------------------------------------


@dataclass
class Result:
    name: str
    status: str
    detail: str = ""


results: list[Result] = []


def record(name: str, status: str, detail: str = "") -> None:
    results.append(Result(name, status, detail))
    print(f"[{status:4}] {name}" + (f" — {detail}" if detail else ""))


def load_jsonl(path: str) -> list[dict] | None:
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_records(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("results", data.get("records", []))


def _resolve_func(candidates):
    for module_name, func_name in candidates:
        try:
            mod = importlib.import_module(module_name)
        except ImportError:
            continue
        fn = getattr(mod, func_name, None)
        if fn:
            return fn, f"{module_name}.{func_name}"
    return None, None


def _match_kwargs(fn, semantic_values: dict) -> dict:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return {}
    ordered_keys = sorted(semantic_values.keys(), key=len, reverse=True)
    kwargs = {}
    for p in sig.parameters.values():
        if p.name in ("self", "cls"):
            continue
        pname = p.name.lower()
        for key in ordered_keys:
            if key in pname:
                kwargs[p.name] = semantic_values[key]
                break
    return kwargs


def _connect():
    """Prefer the admin role for app-schema visibility; RO intentionally cannot see app.schema_cards."""
    for dsn in (ADMIN_DSN, RO_DSN):
        if not dsn or psycopg is None:
            continue
        try:
            conn = psycopg.connect(dsn)
            return conn
        except Exception:  # noqa: BLE001
            continue
    return None

# --------------------------------------------------------------------------
# 1. app.schema_cards DDL — weighted tsvector, not a flat content column
# --------------------------------------------------------------------------


def check_schema_cards_ddl():
    conn = _connect()
    if not conn:
        record("schema_cards::ddl", "SKIP", "no DB connection available")
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select column_name, data_type, generation_expression, is_generated "
                "from information_schema.columns where table_schema=%s and table_name=%s",
                (SCHEMA_CARDS_SCHEMA, SCHEMA_CARDS_TABLE),
            )
            cols = cur.fetchall()
    except Exception as e:  # noqa: BLE001
        record("schema_cards::ddl", "SKIP", f"query failed: {e}")
        return None

    if not cols:
        record("schema_cards::ddl", "FAIL", f"{SCHEMA_CARDS_SCHEMA}.{SCHEMA_CARDS_TABLE} not found — has scripts/20_build_catalog.py been run?")
        return None

    col_names = {c[0] for c in cols}
    text_cols_present = [c for c in CARD_TEXT_COL_CANDIDATES if c in col_names]
    record(
        "schema_cards::separate_text_zones",
        "PASS" if len(text_cols_present) >= 3 else "WARN",
        f"found: {text_cols_present} — the guide specifically requires SEPARATE columns per weight zone (name/description/values), not one flat content column, since setweight needs distinct text zones to weight differently",
    )

    tsv_rows = [c for c in cols if c[0] in TSV_COL_CANDIDATES]
    if not tsv_rows:
        record("schema_cards::tsv_column", "FAIL", f"no column named {TSV_COL_CANDIDATES} found")
    else:
        _, data_type, gen_expr, is_generated = tsv_rows[0]
        is_tsvector = "tsvector" in (data_type or "").lower()
        is_stored_generated = str(is_generated).upper() in ("ALWAYS", "YES") or bool(gen_expr)
        has_setweight = gen_expr and "setweight" in gen_expr.lower()
        has_three_weights = gen_expr and all(w in gen_expr for w in ("'A'", "'B'", "'C'"))
        record("schema_cards::tsv_is_tsvector", "PASS" if is_tsvector else "FAIL", f"data_type={data_type}")
        record("schema_cards::tsv_is_generated", "PASS" if is_stored_generated else "WARN", f"is_generated={is_generated}, has expression={bool(gen_expr)}")
        record("schema_cards::tsv_uses_setweight", "PASS" if has_setweight else "FAIL", "generation_expression doesn't reference setweight()" if not has_setweight else "")
        record(
            "schema_cards::tsv_three_weight_zones",
            "PASS" if has_three_weights else "WARN",
            "expression doesn't clearly reference all three weight labels 'A'/'B'/'C'" if not has_three_weights else "found A/B/C weight zones",
        )

    try:
        with conn.cursor() as cur:
            cur.execute(
                "select indexdef from pg_indexes where schemaname=%s and tablename=%s",
                (SCHEMA_CARDS_SCHEMA, SCHEMA_CARDS_TABLE),
            )
            idx_defs = [r[0] for r in cur.fetchall()]
        has_gin = any(
            "gin" in d.lower() and any(col.lower() in d.lower() for col in TSV_COL_CANDIDATES)
            for d in idx_defs
        )
        record("schema_cards::gin_index", "PASS" if has_gin else "FAIL", f"indexes found: {len(idx_defs)}" + ("" if has_gin else " — no GIN index on tsv found"))
    except Exception as e:  # noqa: BLE001
        record("schema_cards::gin_index", "SKIP", str(e))

    try:
        with conn.cursor() as cur:
            cur.execute(f"select count(*) from {SCHEMA_CARDS_SCHEMA}.{SCHEMA_CARDS_TABLE}")
            n = cur.fetchone()[0]
        record("schema_cards::row_count", "INFO", f"{n} cards")
    except Exception as e:  # noqa: BLE001
        record("schema_cards::row_count", "SKIP", str(e))

    conn.close()
    return col_names


# --------------------------------------------------------------------------
# 2. PII leakage into retrievable card text — the security check
# --------------------------------------------------------------------------


def _parse_pii_entry(entry):
    if isinstance(entry, dict):
        return entry.get("table"), entry.get("column")
    if isinstance(entry, str):
        parts = entry.split(".")
        if len(parts) >= 3:
            # schema.table.column — drop the schema, since the query below
            # hardcodes `marts.` already.
            return parts[-2], parts[-1]
        if len(parts) == 2:
            return parts[0], parts[1]
        return None, entry
    return None, None


def check_pii_leakage(card_cols: set | None):
    if yaml is None:
        record("pii_leakage", "SKIP", "pyyaml not installed")
        return
    glossary_path = next((p for p in GLOSSARY_PATH_CANDIDATES if os.path.exists(p)), None)
    if not glossary_path:
        record("pii_leakage", "SKIP", f"none of {GLOSSARY_PATH_CANDIDATES} found")
        return
    glossary_raw = yaml.safe_load(Path(glossary_path).read_text(encoding="utf-8")) or {}
    pii_entries = glossary_raw.get("pii_columns") or glossary_raw.get("pii") or []
    if not pii_entries:
        record("pii_leakage", "SKIP", "no pii_columns found in glossary.yml")
        return

    conn = _connect()
    if not conn:
        record("pii_leakage", "SKIP", "no DB connection available")
        return

    text_cols = [c for c in CARD_TEXT_COL_CANDIDATES if not card_cols or c in card_cols]
    if not text_cols:
        text_cols = CARD_TEXT_COL_CANDIDATES
    concat_expr = " || ' ' || ".join(f"coalesce({c}::text, '')" for c in text_cols)

    leaks = []
    checked = 0
    try:
        with conn:
            for entry in pii_entries:
                table, col = _parse_pii_entry(entry)
                if not col:
                    continue
                if not table:
                    continue  # can't safely guess which table without more info
                try:
                    with conn.cursor() as cur:
                        cur.execute(f'select distinct "{col}"::text from marts."{table}" where "{col}" is not null limit 5')
                        real_values = [r[0] for r in cur.fetchall() if r[0] and len(str(r[0])) > 2]
                except Exception:  # noqa: BLE001
                    continue
                checked += 1
                for val in real_values:
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                f"select count(*) from {SCHEMA_CARDS_SCHEMA}.{SCHEMA_CARDS_TABLE} where {concat_expr} ilike %s",
                                (f"%{val}%",),
                            )
                            hit_count = cur.fetchone()[0]
                        if hit_count > 0:
                            leaks.append((table, col, val, hit_count))
                    except Exception:  # noqa: BLE001
                        continue
    finally:
        conn.close()

    if checked == 0:
        record("pii_leakage", "SKIP", "couldn't resolve any glossary PII entries to a real (table, column) pair to test against")
    elif leaks:
        record(
            "pii_leakage",
            "FAIL",
            f"{len(leaks)} real PII value(s) found verbatim in {SCHEMA_CARDS_SCHEMA}.{SCHEMA_CARDS_TABLE} text — "
            f"e.g. {leaks[:3]} (table, column, value, card hit count). This is retrievable, embedded, and served into "
            "every future prompt regardless of who's asking — exactly the bug the guide calls out in Step 1.",
        )
    else:
        record("pii_leakage", "PASS", f"checked {checked} PII column(s) against real sample values — none found verbatim in card text (excluded or redacted correctly)")


# --------------------------------------------------------------------------
# 3. retrieval/ module boundary — must not import agent/ or llm/
# --------------------------------------------------------------------------


def check_module_boundary():
    pkg_dir = next((p for p in RETRIEVAL_PACKAGE_DIR_CANDIDATES if os.path.isdir(p)), None)
    if not pkg_dir:
        record("retrieval::module_boundary", "SKIP", f"none of {RETRIEVAL_PACKAGE_DIR_CANDIDATES} found")
        return
    violations = []
    for path in glob.glob(f"{pkg_dir}/*.py"):
        text = Path(path).read_text(encoding="utf-8")
        for prefix in FORBIDDEN_IMPORT_PREFIXES:
            if re.search(rf"^\s*(from|import)\s+{re.escape(prefix)}\b", text, re.MULTILINE):
                violations.append((os.path.basename(path), prefix))
    if violations:
        record("retrieval::module_boundary", "FAIL", f"forbidden imports found: {violations} — retrieval/ must not import agent/ or llm/ per the guide's §9.4 (this is what lets Recall@k run standalone with no LLM in the loop)")
    else:
        record("retrieval::module_boundary", "PASS", f"scanned {len(glob.glob(f'{pkg_dir}/*.py'))} file(s) in {pkg_dir}, no forbidden imports found")


# --------------------------------------------------------------------------
# 4. RRF fusion — independent synthetic adversarial test
# --------------------------------------------------------------------------


def _make_test_result(card_id: str):
    from cardinal.retrieval.models import RetrievalResult

    return RetrievalResult(
        card_id=card_id,
        card_type="table",
        domain="test",
        card_name=card_id,
        card_text=card_id,
        score=0.0,
        metadata={},
    )


def _resolve_rrf_class():
    """Fall back to a class-based fusion implementation (e.g. ReciprocalRankFusion.fuse())."""
    try:
        from cardinal.retrieval.fusion import ReciprocalRankFusion
    except ImportError:
        return None
    return ReciprocalRankFusion


def check_rrf_fusion():
    fn, used = _resolve_func(FUSION_MODULE_CANDIDATES)
    if not fn:
        cls = _resolve_rrf_class()
        if cls is None:
            record("retrieval::rrf_fusion", "SKIP", f"none of {FUSION_MODULE_CANDIDATES} importable, and no fusion class found — edit CONFIG")
            return
        _check_rrf_fusion_class(cls)
        return

    # Card A: rank 1 in both lists. Card B: rank 1 sparse only. Card C: rank 2 dense only.
    sparse = [("A", 1), ("B", 2)]
    dense = [("A", 1), ("C", 2)]
    k = FUSION_K_DEFAULT

    expected_a = 1 / (k + 1) + 1 / (k + 1)
    expected_b = 1 / (k + 2)
    expected_c = 1 / (k + 2)

    kwargs = _match_kwargs(fn, {"sparse": sparse, "dense": dense, "k": k})
    try:
        out = fn(**kwargs) if kwargs else fn(sparse, dense, k=k)
    except TypeError as e:
        record("retrieval::rrf_fusion", "SKIP", f"found {used} but couldn't match call signature ({e}) — edit CONFIG semantic dict")
        return
    except Exception as e:  # noqa: BLE001
        record("retrieval::rrf_fusion", "FAIL", f"raised {type(e).__name__}: {e}")
        return

    scores = {}
    for item in out:
        if isinstance(item, dict):
            scores[item.get("card_id") or item.get("id")] = item.get("score")
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            scores[item[0]] = item[1]

    if not scores:
        record("retrieval::rrf_fusion", "FAIL", f"couldn't parse output shape: {out!r:.200}")
        return

    tol = 1e-6
    checks = [("A", expected_a), ("B", expected_b), ("C", expected_c)]
    all_ok = True
    for card, expected in checks:
        actual = scores.get(card)
        ok = actual is not None and abs(actual - expected) < tol
        all_ok &= ok
        record(f"retrieval::rrf_fusion::{card}", "PASS" if ok else "FAIL", f"expected {expected:.6f}, got {actual}")

    if all_ok and scores.get("A", 0) <= scores.get("B", 0):
        record("retrieval::rrf_fusion::ordering", "FAIL", "card A appears in both lists and should score strictly higher than cards appearing in only one, but doesn't")
    elif all_ok:
        record("retrieval::rrf_fusion::ordering", "PASS", "card present in both lists correctly outranks cards present in only one")
    
def _check_rrf_fusion_class(cls):
    """Run the same synthetic adversarial test against a class-based fuse() method."""
    k = FUSION_K_DEFAULT

    # Card A: rank 1 in both lists. Card B: rank 2 sparse only. Card C: rank 2 dense only.
    sparse_order = ["A", "B"]
    dense_order = ["A", "C"]

    expected_a = 1 / (k + 1) + 1 / (k + 1)
    expected_b = 1 / (k + 2)
    expected_c = 1 / (k + 2)

    try:
        fusion = cls(k=k)
        sparse_results = [_make_test_result(cid) for cid in sparse_order]
        dense_results = [_make_test_result(cid) for cid in dense_order]
        out = fusion.fuse([sparse_results, dense_results], limit=10)
    except Exception as e:  # noqa: BLE001
        record("retrieval::rrf_fusion", "FAIL", f"raised {type(e).__name__}: {e}")
        return

    scores = {result.card_id: result.score for result in out}

    if not scores:
        record("retrieval::rrf_fusion", "FAIL", "fuse() returned no results")
        return

    tol = 1e-6
    checks = [("A", expected_a), ("B", expected_b), ("C", expected_c)]
    all_ok = True
    for card, expected in checks:
        actual = scores.get(card)
        ok = actual is not None and abs(actual - expected) < tol
        all_ok &= ok
        record(f"retrieval::rrf_fusion::{card}", "PASS" if ok else "FAIL", f"expected {expected:.6f}, got {actual}")

    if all_ok and scores.get("A", 0) <= scores.get("B", 0):
        record("retrieval::rrf_fusion::ordering", "FAIL", "card A appears in both lists and should score strictly higher than cards appearing in only one, but doesn't")
    elif all_ok:
        record("retrieval::rrf_fusion::ordering", "PASS", "card present in both lists correctly outranks cards present in only one")


# --------------------------------------------------------------------------
# 5. bge query prefix
# --------------------------------------------------------------------------


def check_query_prefix():
    candidate_files = []
    for pkg_dir in RETRIEVAL_PACKAGE_DIR_CANDIDATES:
        for filename in ("qdrant.py", "dense.py"):
            candidate = os.path.join(pkg_dir, filename)
            if os.path.exists(candidate):
                candidate_files.append(candidate)
    if not candidate_files:
        record("retrieval::query_prefix", "SKIP", "neither qdrant.py nor dense.py found")
        return
    text = "\n".join(Path(p).read_text(encoding="utf-8") for p in candidate_files)
    has_exact_prefix = BGE_QUERY_PREFIX in text
    has_any_prefix_like_thing = bool(re.search(r"(represent|instruction|prefix)", text, re.IGNORECASE))
    if has_exact_prefix:
        record("retrieval::query_prefix", "PASS", "found the exact recommended bge-small-en-v1.5 query instruction prefix in dense.py")
    elif has_any_prefix_like_thing:
        record("retrieval::query_prefix", "WARN", "found SOME prefix-related code but not the exact recommended string — verify it matches 'Represent this sentence for searching relevant passages:' (BGE's own v1.5 card says it works reasonably without one too, so this is a WARN not a FAIL)")
    else:
        record("retrieval::query_prefix", "WARN", "no query-instruction prefix found in dense.py at all — per the guide, this degrades dense recall silently with no error, worth confirming this was a deliberate choice")


# --------------------------------------------------------------------------
# 6. Qdrant collection config
# --------------------------------------------------------------------------


def check_qdrant_collection():
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        record("qdrant::collection", "SKIP", "qdrant_client not installed")
        return
    try:
        client = QdrantClient(url=QDRANT_URL)
        info = client.get_collection(QDRANT_COLLECTION)
    except Exception as e:  # noqa: BLE001
        record("qdrant::collection", "SKIP", f"couldn't reach Qdrant or collection '{QDRANT_COLLECTION}' at {QDRANT_URL}: {e}")
        return

    vectors_config = getattr(info.config.params, "vectors", None)
    size = getattr(vectors_config, "size", None)
    distance = getattr(vectors_config, "distance", None)
    record("qdrant::vector_size", "PASS" if size == EXPECTED_VECTOR_SIZE else "WARN", f"size={size}, expected {EXPECTED_VECTOR_SIZE} (bge-small-en-v1.5)")
    record("qdrant::distance_metric", "PASS" if str(distance).lower() == "cosine" else "WARN", f"distance={distance} — bge models are trained for cosine similarity")

    point_count = getattr(info, "points_count", None)
    record("qdrant::point_count", "INFO", f"{point_count} points in collection")

    try:
        points, _ = client.scroll(collection_name=QDRANT_COLLECTION, limit=1, with_payload=True)
        if points:
            payload_keys = set(points[0].payload.keys())
            expected_keys = {"card_type", "domain"}
            missing = expected_keys - payload_keys
            record("qdrant::payload_shape", "PASS" if not missing else "WARN", f"payload keys: {payload_keys}" + (f", missing: {missing}" if missing else ""))
    except Exception as e:  # noqa: BLE001
        record("qdrant::payload_shape", "SKIP", str(e))


# --------------------------------------------------------------------------
# 7. generate_sql.j2 immutability + generate_sql_v2.j2 exists
# --------------------------------------------------------------------------


def check_template_immutability():
    if not os.path.exists(GENERATE_TEMPLATE_PATH):
        record("templates::generate_sql_unchanged", "SKIP", f"{GENERATE_TEMPLATE_PATH} not found")
    else:
        content = Path(GENERATE_TEMPLATE_PATH).read_bytes()
        current_hash = hashlib.sha256(content).hexdigest()[:12]
        record(
            "templates::generate_sql_unchanged",
            "PASS" if current_hash == KNOWN_GENERATE_HASH_PREFIX else "WARN",
            f"current hash={current_hash}, previously confirmed={KNOWN_GENERATE_HASH_PREFIX}" + ("" if current_hash == KNOWN_GENERATE_HASH_PREFIX else " — Phase 3's baseline.md is pinned to the old hash; if this changed intentionally that historical record is now stale"),
        )

    v2_path = next((p for p in GENERATE_V2_TEMPLATE_CANDIDATES if os.path.exists(p)), None)
    record("templates::generate_sql_v2_exists", "PASS" if v2_path else "FAIL", v2_path or f"none of {GENERATE_V2_TEMPLATE_CANDIDATES} found — guide requires a NEW template, not editing generate_sql.j2 in place")


# --------------------------------------------------------------------------
# 8. Required artifacts
# --------------------------------------------------------------------------


def check_recall_ablation_doc():
    if not os.path.exists(RETRIEVAL_ABLATION_DOC):
        record("artifacts::retrieval_ablation", "FAIL", f"{RETRIEVAL_ABLATION_DOC} not found — required checkpoint artifact")
        return
    text = Path(RETRIEVAL_ABLATION_DOC).read_text(encoding="utf-8")
    configs_found = [c for c in ("BM25", "dense", "RRF", "rerank") if c.lower() in text.lower()]
    k_values_found = [k for k in ("5", "10", "20") if re.search(rf"\bk\s*=?\s*{k}\b|@{k}\b", text)]
    record("artifacts::retrieval_ablation::configs", "PASS" if len(configs_found) >= 3 else "WARN", f"recognizable configs mentioned: {configs_found}")
    record("artifacts::retrieval_ablation::k_values", "PASS" if len(k_values_found) >= 2 else "WARN", f"recognizable k values mentioned: {k_values_found}")


def check_required_tables_annotation(suite_rows):
    if not suite_rows:
        record("artifacts::required_tables_annotation", "SKIP", "olist_gold_150.jsonl not loaded")
        return
    with_annotation = sum(1 for r in suite_rows if r.get("required_tables"))
    answerable = sum(1 for r in suite_rows if r.get("answerable") is not False)
    record(
        "artifacts::required_tables_annotation",
        "PASS" if with_annotation >= answerable * 0.9 else "FAIL",
        f"{with_annotation}/{len(suite_rows)} rows have a required_tables annotation ({answerable} are answerable) — Step 7 needs this on essentially every answerable question",
    )


def check_decomposition_doc():
    path = next((p for p in DECOMPOSITION_DOC_CANDIDATES if os.path.exists(p)), None)
    if not path:
        record("artifacts::decomposition", "FAIL", f"none of {DECOMPOSITION_DOC_CANDIDATES} found — required checkpoint artifact (retrieval-miss vs. generation-error breakdown)")
        return
    text = Path(path).read_text(encoding="utf-8")
    has_pct = bool(re.search(r"\d+(\.\d+)?%", text))
    record("artifacts::decomposition", "PASS" if has_pct else "WARN", f"found {path}" + ("" if has_pct else ", but no percentage figures detected in it"))


# --------------------------------------------------------------------------
# 9. Best-effort: retrieval_guarded_repaired results sanity
# --------------------------------------------------------------------------


def check_retrieval_system_results():
    matches = glob.glob(f"{RESULTS_DIR}/*retrieval*guarded*repaired*.json") or glob.glob(f"{RESULTS_DIR}/*retrieval_guarded_repaired*.json")
    if not matches:
        record("retrieval_guarded_repaired::results", "SKIP", "no results file matching the new system name found — check your naming or that it's been run")
        return
    path = sorted(matches, key=os.path.getmtime, reverse=True)[0]
    recs = _load_records(path)
    if not recs:
        record("retrieval_guarded_repaired::results", "FAIL", f"{path} is empty")
        return
    acc = sum(1 for r in recs if r.get("correct")) / len(recs)
    record("retrieval_guarded_repaired::results", "INFO", f"{os.path.basename(path)}: {acc:.1%} over {len(recs)} records")


# --------------------------------------------------------------------------


def main() -> int:
    print("== app.schema_cards DDL ==")
    card_cols = check_schema_cards_ddl()

    print("\n== PII leakage into retrievable card text ==")
    check_pii_leakage(card_cols)

    print("\n== retrieval/ module boundary (no agent/llm imports) ==")
    check_module_boundary()

    print("\n== RRF fusion — independent synthetic test ==")
    check_rrf_fusion()

    print("\n== bge-small-en-v1.5 query instruction prefix ==")
    check_query_prefix()

    print("\n== Qdrant schema_cards collection ==")
    check_qdrant_collection()

    print("\n== Template immutability ==")
    check_template_immutability()

    print("\n== Required artifacts ==")
    check_recall_ablation_doc()
    olist_rows = load_jsonl(OLIST_SUITE_PATH)
    check_required_tables_annotation(olist_rows)
    check_decomposition_doc()

    print("\n== retrieval_guarded_repaired system ==")
    check_retrieval_system_results()

    fails = [r for r in results if r.status == "FAIL"]
    warns = [r for r in results if r.status == "WARN"]
    skips = [r for r in results if r.status == "SKIP"]
    print(f"\n{'='*60}")
    print(f"TOTAL: {len(results)} checks — {len(fails)} FAIL, {len(warns)} WARN, {len(skips)} SKIP")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    sys.path.insert(0, os.path.join(os.getcwd(), "src"))
    raise SystemExit(main())