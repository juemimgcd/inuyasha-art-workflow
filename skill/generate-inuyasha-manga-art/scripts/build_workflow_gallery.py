#!/usr/bin/env python3
"""Build and optionally serve the read-only local reference gallery."""

from __future__ import annotations

import argparse
import json
import shlex
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from build_reference_index import freshness
from task_workflow import feedback_rank, reference_performance
from workflow_common import (
    atomic_write_json,
    atomic_write_text,
    library_signature,
    load_config,
    open_database,
    resolve_recorded_path,
    workflow_paths,
    workflow_root,
)

THUMBNAIL_MAX_EDGE = 480
VISIBLE_DOMAINS = ("identity", "character-style", "scene", "continuity")
JSON_FIELDS = {
    "subjects": list,
    "forms": list,
    "subject_forms": dict,
    "shot_types": list,
    "tags": list,
    "eligible_roles": list,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument(
        "--query-results",
        type=Path,
        help="Optional JSON output from an existing retrieval CLI.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Serve the generated gallery with the standard-library HTTP server.",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def ensure_safe_output(gallery: Path, config: dict) -> None:
    resolved = gallery.resolve()
    for source in config.get("sources", []):
        source_root = Path(source["path"]).resolve()
        if is_within(resolved, source_root):
            raise ValueError(f"gallery output cannot be inside source library: {source_root}")


def parse_json_field(row: dict, field: str, expected_type: type):
    value = json.loads(row[field])
    if not isinstance(value, expected_type):
        raise ValueError(f"{field} must decode to {expected_type.__name__}")
    return value


def trait_values(tags: list[str], prefix: str) -> list[str]:
    marker = f"{prefix}:"
    return sorted(
        {tag[len(marker) :] for tag in tags if isinstance(tag, str) and tag.startswith(marker)},
        key=str.casefold,
    )


def retrieval_query(item: dict) -> str | None:
    source_id = item["source_id"]
    if source_id == "manga-curated":
        args = ["--medium", "manga"]
    elif source_id == "tv-curated":
        args = ["--medium", "tv"]
    elif source_id == "selected-output":
        args = ["--source", "selected-output"]
    else:
        return None

    domain = item["reference_domain"]
    args += ["--reference-domain", domain]
    pairs = [
        (subject, form)
        for subject, forms in item["subject_forms"].items()
        for form in forms
    ]
    if domain in {"character-style", "scene"}:
        args += ["--role", "rendering"]
    if domain == "character-style" and pairs:
        args += ["--prefer-subject-form", f"{pairs[0][0]}={pairs[0][1]}"]
    elif item["subjects"]:
        args += ["--subject", item["subjects"][0]]
    if item["shot_types"]:
        args += ["--shot", item["shot_types"][0]]
    if item["view_angles"] and domain != "scene":
        args += ["--view-angle", item["view_angles"][0]]
    if item["scene_ids"]:
        args += ["--exact-term", f"scene-id:{item['scene_ids'][0]}"]
    command = [
        "scripts/run-python",
        "scripts/browse_curated_styles.py",
        *args,
        "--json",
    ]
    return " ".join(shlex.quote(value) for value in command)


def load_query_results(path: Path | None) -> tuple[dict | None, dict[str, dict]]:
    if path is None:
        return None, {}
    payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("query results must be a JSON object")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("query results must contain a candidates list")
    results = {}
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("item_id"), str):
            raise ValueError("every query candidate must contain an item_id")
        reasons = candidate.get("match_reasons", [])
        if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons):
            raise ValueError("query candidate match_reasons must be a string list")
        results[candidate["item_id"]] = {
            "score": candidate.get("score"),
            "match_reasons": reasons,
            "position": candidate.get("position"),
        }
    context_keys = (
        "source_id",
        "reference_domain",
        "medium",
        "query",
        "intent_text",
        "exact_terms",
        "subjects",
        "forms",
        "preferred_subject_forms",
        "shots",
        "view_angle",
        "role",
    )
    return {key: payload.get(key) for key in context_keys}, results


def make_thumbnail(source: Path, destination: Path) -> None:
    if destination.is_file():
        return
    with Image.open(source) as image:
        rendered = ImageOps.exif_transpose(image)
        rendered.thumbnail((THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE), Image.Resampling.LANCZOS)
        if rendered.mode != "RGB":
            background = Image.new("RGB", rendered.size, "white")
            if "A" in rendered.getbands():
                background.paste(rendered, mask=rendered.getchannel("A"))
            else:
                background.paste(rendered.convert("RGB"))
            rendered = background
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        rendered.save(temporary, format="JPEG", quality=84, optimize=True)
        temporary.replace(destination)


def read_references(config: dict, root: Path, gallery: Path, query_path: Path | None) -> dict:
    paths = workflow_paths(root)
    database = paths["database"]
    if not database.is_file():
        raise FileNotFoundError(f"catalog missing: {database}")
    fresh, reason = freshness(
        database, config, library_signature(config), paths["annotations"]
    )
    if not fresh:
        raise RuntimeError(
            f"Catalog is stale: {reason}; run build_reference_index.py"
        )
    query_context, query_items = load_query_results(query_path)
    performance = reference_performance(paths["tasks"])
    connection = open_database(database, read_only=True)
    placeholders = ",".join("?" for _ in VISIBLE_DOMAINS)
    rows = connection.execute(
        f"""
        SELECT items.item_id, items.source_id, items.reference_domain,
               items.path, items.relative_path, items.content_hash,
               items.content_label, items.subjects, items.forms,
               items.subject_forms, items.shot_types, items.tags,
               items.eligible_roles, items.width, items.height,
               sources.label AS source_label, sources.medium
        FROM items
        JOIN sources USING (source_id)
        WHERE items.kind = 'image'
          AND items.reference_domain IN ({placeholders})
        ORDER BY items.relative_path COLLATE NOCASE, items.item_id
        """,
        VISIBLE_DOMAINS,
    ).fetchall()
    connection.close()

    thumbnails = gallery / "thumbnails"
    items = []
    errors = []
    for raw_row in rows:
        row = dict(raw_row)
        try:
            for field, expected_type in JSON_FIELDS.items():
                row[field] = parse_json_field(row, field, expected_type)
            if not row["content_hash"]:
                raise ValueError("content_hash is missing")
            row["view_angles"] = trait_values(row["tags"], "view-angle")
            row["scene_ids"] = trait_values(row["tags"], "scene-id")
            row["scene_economy"] = trait_values(row["tags"], "scene-economy")
            row["black_mass"] = trait_values(row["tags"], "black-mass")
            row["tone_density"] = trait_values(row["tags"], "tone-density")
            row["detail_falloff"] = trait_values(row["tags"], "detail-falloff")
            row["certified_style_anchor"] = "style-anchor:certified" in row["tags"]
            stats = performance.get(
                row["item_id"],
                {"accepted": 0, "rejected": 0, "total": 0, "smoothed_acceptance": 0.5},
            )
            row["reference_outcomes"] = {
                **stats,
                "feedback_rank": round(feedback_rank(stats), 4),
            }
            row["retrieval"] = query_items.get(row["item_id"])
            source = resolve_recorded_path(row["path"], config)
            row["source_path"] = str(source)
            thumbnail = thumbnails / f"{row['content_hash']}.jpg"
            try:
                if not source.is_file():
                    raise FileNotFoundError(f"source image is missing: {source}")
                make_thumbnail(source, thumbnail)
                row["thumbnail"] = f"thumbnails/{thumbnail.name}"
                row["image_error"] = None
            except (FileNotFoundError, OSError, UnidentifiedImageError) as exc:
                row["thumbnail"] = None
                row["image_error"] = str(exc)
                errors.append({"item_id": row["item_id"], "error": str(exc)})
            row["browse_query"] = retrieval_query(row)
            row["invalid"] = False
            row.pop("path", None)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            row = {
                "item_id": str(row.get("item_id", "unknown")),
                "relative_path": str(row.get("relative_path", "")),
                "invalid": True,
                "data_error": str(exc),
                "thumbnail": None,
            }
            errors.append({"item_id": row["item_id"], "error": str(exc)})
        items.append(row)
    return {
        "schema_version": 1,
        "catalog_path": str(database),
        "count": len(items),
        "query_context": query_context,
        "query_result_count": len(query_items),
        "errors": errors,
        "items": items,
    }


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Inuyasha Workflow References</title>
  <style>
    :root { color-scheme: light; --ink:#191714; --paper:#f7f3e9; --panel:#fffdf7; --line:#c9c0ae; --muted:#6d665a; --accent:#8b201e; --focus:#2458a6; }
    * { box-sizing:border-box; }
    [hidden] { display:none !important; }
    body { margin:0; color:var(--ink); background:var(--paper); font:15px/1.45 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    button,input,select { font:inherit; }
    button,select,input { border:1px solid var(--line); border-radius:6px; background:#fff; color:var(--ink); }
    button { padding:.58rem .78rem; cursor:pointer; }
    button:hover:not(:disabled) { border-color:var(--accent); color:var(--accent); }
    button:disabled { cursor:not-allowed; opacity:.48; }
    :focus-visible { outline:3px solid color-mix(in srgb,var(--focus) 55%,transparent); outline-offset:2px; }
    header { padding:1.25rem clamp(1rem,3vw,2.5rem); border-bottom:1px solid var(--line); background:var(--panel); }
    h1 { margin:0; font:700 clamp(1.55rem,3vw,2.25rem)/1.1 ui-serif,Georgia,serif; }
    header p { max-width:68rem; margin:.55rem 0 0; color:var(--muted); }
    main { padding:1rem clamp(1rem,3vw,2.5rem) 3rem; }
    .filters { display:grid; grid-template-columns:minmax(14rem,2fr) repeat(3,minmax(9rem,1fr)); gap:.75rem; padding:1rem; border:1px solid var(--line); border-radius:10px; background:var(--panel); }
    .field { display:grid; align-content:start; gap:.3rem; min-width:0; }
    .field label { color:var(--muted); font-size:.82rem; font-weight:650; }
    .field input,.field select { width:100%; min-height:2.45rem; padding:.5rem .6rem; }
    .filter-actions { display:flex; align-items:end; gap:.5rem; }
    .check { display:flex; align-items:center; gap:.48rem; padding:.45rem 0; }
    .check input { inline-size:1.05rem; block-size:1.05rem; }
    .meta { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:.7rem; min-height:3.4rem; color:var(--muted); }
    .state { padding:2rem; border:1px dashed var(--line); border-radius:10px; background:var(--panel); text-align:center; }
    .state[hidden] { display:none; }
    .error { color:#8a1715; }
    .grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1rem; }
    .card { min-width:0; overflow:hidden; border:1px solid var(--line); border-radius:10px; background:var(--panel); }
    .thumb { display:grid; place-items:center; inline-size:100%; aspect-ratio:4/3; overflow:hidden; border-bottom:1px solid var(--line); background:#e9e2d4; }
    .thumb img { inline-size:100%; block-size:100%; object-fit:contain; }
    .placeholder { max-width:22rem; padding:1rem; color:var(--muted); text-align:center; }
    .card-body { display:grid; gap:.7rem; padding:.9rem; }
    .eyebrow { color:var(--accent); font-size:.76rem; font-weight:750; letter-spacing:.04em; text-transform:uppercase; }
    .item-id { margin:0; overflow-wrap:anywhere; font:650 .95rem/1.35 ui-monospace,SFMono-Regular,Menlo,monospace; }
    .path { margin:0; color:var(--muted); overflow-wrap:anywhere; }
    .chips { display:flex; flex-wrap:wrap; gap:.35rem; }
    .chip { max-width:100%; padding:.18rem .42rem; border:1px solid var(--line); border-radius:999px; overflow-wrap:anywhere; background:#fff; font-size:.75rem; }
    .outcome { display:flex; gap:.8rem; color:var(--muted); font-size:.82rem; }
    .card button { justify-self:start; }
    dialog { width:min(54rem,calc(100% - 2rem)); max-height:calc(100dvh - 2rem); padding:0; border:1px solid var(--line); border-radius:12px; color:var(--ink); background:var(--panel); box-shadow:0 18px 50px #0003; }
    dialog::backdrop { background:#17130f99; }
    .dialog-head { position:sticky; top:0; display:flex; justify-content:space-between; gap:1rem; padding:1rem; border-bottom:1px solid var(--line); background:var(--panel); z-index:1; }
    .dialog-head h2 { margin:0; overflow-wrap:anywhere; font-size:1.05rem; }
    .dialog-body { display:grid; gap:1rem; padding:1rem; }
    .detail-image { max-width:100%; max-height:60dvh; margin:auto; object-fit:contain; background:#eee8da; }
    dl { display:grid; grid-template-columns:minmax(9rem,13rem) 1fr; gap:.55rem 1rem; margin:0; }
    dt { color:var(--muted); font-weight:650; }
    dd { margin:0; min-width:0; overflow-wrap:anywhere; }
    pre { overflow:auto; margin:0; padding:.8rem; border:1px solid var(--line); border-radius:6px; background:#f1ece1; white-space:pre-wrap; word-break:break-word; }
    .copy-actions { display:flex; flex-wrap:wrap; gap:.5rem; }
    @media (max-width:1050px) { .filters { grid-template-columns:repeat(3,minmax(0,1fr)); } .field.search { grid-column:1/-1; } .grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
    @media (max-width:700px) { .filters { grid-template-columns:1fr; } .field.search { grid-column:auto; } .grid { grid-template-columns:1fr; } dl { grid-template-columns:1fr; gap:.15rem; } dd { margin-bottom:.55rem; } }
  </style>
</head>
<body>
  <header>
    <h1>References</h1>
    <p>catalog.sqlite3 的只读派生视图。浏览不改变参考图、标注、manifest、attempt 或偏好数据。</p>
  </header>
  <main>
    <section class="filters" aria-label="参考图筛选">
      <div class="field search"><label for="search">搜索路径、ID、标签或内容</label><input id="search" type="search" disabled autocomplete="off"></div>
      <div class="field"><label for="medium">媒介</label><select id="medium" disabled><option value="">全部</option><option value="manga">Manga</option><option value="tv">TV</option></select></div>
      <div class="field"><label for="domain">Authority domain</label><select id="domain" disabled><option value="">全部</option><option>identity</option><option>character-style</option><option>scene</option><option>continuity</option></select></div>
      <div class="field"><label for="subject">角色 / subject</label><select id="subject" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="form">精确 form</label><select id="form" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="shot">Shot</label><select id="shot" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="view">View angle</label><select id="view" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="sceneId">Canonical scene ID</label><select id="sceneId" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="sceneEconomy">Scene economy</label><select id="sceneEconomy" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="blackMass">Black mass</label><select id="blackMass" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="tone">Tone density</label><select id="tone" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="falloff">Detail falloff</label><select id="falloff" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="role">Eligible role</label><select id="role" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="outcome">历史 reference use</label><select id="outcome" disabled><option value="">全部</option><option value="accepted">Accepted use</option><option value="rejected">Explicitly blamed rejection</option><option value="unused">No decided use</option></select></div>
      <div class="field">
        <label>布尔筛选</label>
        <label class="check"><input id="certified" type="checkbox" disabled> Certified style anchor</label>
        <label class="check"><input id="negativeSpace" type="checkbox" disabled> Authored negative space</label>
        <label class="check" id="queryOnlyRow" hidden><input id="queryOnly" type="checkbox" disabled checked> 只看传入检索结果</label>
      </div>
      <div class="filter-actions"><button id="clear" type="button" disabled>清除筛选</button></div>
    </section>
    <div class="meta"><span id="status" role="status" aria-live="polite">正在读取 references.json…</span><span id="queryContext"></span></div>
    <section id="loading" class="state">正在加载参考图索引…</section>
    <section id="empty" class="state" hidden>没有符合当前筛选条件的参考图。</section>
    <section id="error" class="state error" hidden></section>
    <section id="grid" class="grid" aria-label="参考图结果"></section>
  </main>
  <dialog id="detail"><div class="dialog-head"><h2 id="detailTitle"></h2><button id="closeDetail" type="button">关闭</button></div><div id="detailBody" class="dialog-body"></div></dialog>
  <script>
    const ids = ["search","medium","domain","subject","form","shot","view","sceneId","sceneEconomy","blackMass","tone","falloff","role","outcome","certified","negativeSpace","queryOnly"];
    const controls = Object.fromEntries(ids.map(id => [id, document.getElementById(id)]));
    const state = { items: [], byId: new Map(), queryContext: null, current: null };
    const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
    const chips = values => `<div class="chips">${values.map(value => `<span class="chip">${esc(value)}</span>`).join("")}</div>`;
    const unique = (items, key) => [...new Set(items.flatMap(item => item.invalid ? [] : item[key] || []))].sort((a,b) => a.localeCompare(b));
    function populate(id, values) { controls[id].insertAdjacentHTML("beforeend", values.map(value => `<option value="${esc(value)}">${esc(value)}</option>`).join("")); }
    function searchable(item) { return [item.item_id,item.relative_path,item.content_label,item.source_label,...(item.tags||[]),...(item.subjects||[]),...(item.forms||[])].join(" ").toLocaleLowerCase(); }
    function matches(item) {
      if (item.invalid) return !controls.search.value || searchable(item).includes(controls.search.value.toLocaleLowerCase());
      const subject = controls.subject.value, form = controls.form.value;
      if (controls.search.value && !searchable(item).includes(controls.search.value.toLocaleLowerCase())) return false;
      if (controls.medium.value && item.medium !== controls.medium.value) return false;
      if (controls.domain.value && item.reference_domain !== controls.domain.value) return false;
      if (subject && !(item.subjects||[]).includes(subject)) return false;
      if (form && (subject ? !(item.subject_forms?.[subject]||[]).includes(form) : !(item.forms||[]).includes(form))) return false;
      if (controls.shot.value && !(item.shot_types||[]).includes(controls.shot.value)) return false;
      if (controls.view.value && !(item.view_angles||[]).includes(controls.view.value)) return false;
      if (controls.sceneId.value && !(item.scene_ids||[]).includes(controls.sceneId.value)) return false;
      if (controls.sceneEconomy.value && !(item.scene_economy||[]).includes(controls.sceneEconomy.value)) return false;
      if (controls.blackMass.value && !(item.black_mass||[]).includes(controls.blackMass.value)) return false;
      if (controls.tone.value && !(item.tone_density||[]).includes(controls.tone.value)) return false;
      if (controls.falloff.value && !(item.detail_falloff||[]).includes(controls.falloff.value)) return false;
      if (controls.role.value && !(item.eligible_roles||[]).includes(controls.role.value)) return false;
      if (controls.certified.checked && !item.certified_style_anchor) return false;
      if (controls.negativeSpace.checked && !(item.scene_economy||[]).includes("authored-negative-space")) return false;
      if (state.queryContext && controls.queryOnly.checked && !item.retrieval) return false;
      const stats = item.reference_outcomes || {};
      if (controls.outcome.value === "accepted" && !stats.accepted) return false;
      if (controls.outcome.value === "rejected" && !stats.rejected) return false;
      if (controls.outcome.value === "unused" && stats.total) return false;
      return true;
    }
    function render() {
      const visible = state.items.filter(matches);
      document.getElementById("grid").innerHTML = visible.map(item => item.invalid ? `
        <article class="card"><div class="thumb"><div class="placeholder error">Invalid catalog row</div></div><div class="card-body"><p class="item-id">${esc(item.item_id)}</p><p class="path">${esc(item.data_error)}</p></div></article>` : `
        <article class="card">
          <div class="thumb">${item.thumbnail ? `<img src="${esc(item.thumbnail)}" alt="${esc(item.content_label || item.relative_path)}" loading="lazy">` : `<div class="placeholder error">${esc(item.image_error || "Missing image")}</div>`}</div>
          <div class="card-body"><div class="eyebrow">${esc(item.reference_domain)} · ${esc(item.medium)}</div><h2 class="item-id">${esc(item.item_id)}</h2><p class="path">${esc(item.content_label || item.relative_path)}</p>
          ${chips([...(item.subjects||[]),...(item.forms||[]),...(item.shot_types||[]),...(item.view_angles||[]).map(v=>`view:${v}`)].slice(0,10))}
          <div class="outcome"><span>accepted ${item.reference_outcomes.accepted}</span><span>rejected ${item.reference_outcomes.rejected}</span><span>smoothed ${item.reference_outcomes.smoothed_acceptance}</span></div>
          ${item.retrieval ? `<p class="path">检索命中：${esc((item.retrieval.match_reasons||[]).join("；") || "无记录理由")}</p>` : ""}
          <button type="button" data-detail="${esc(item.item_id)}">查看详情</button></div>
        </article>`).join("");
      document.getElementById("empty").hidden = visible.length !== 0;
      document.getElementById("status").textContent = `显示 ${visible.length} / ${state.items.length} 项`;
      const params = new URLSearchParams();
      for (const [id, control] of Object.entries(controls)) { const value = control.type === "checkbox" ? (control.checked ? "1" : "") : control.value; if (value) params.set(id,value); }
      history.replaceState(null,"",`${location.pathname}${params.size ? `?${params}` : ""}`);
    }
    function showDetail(item) {
      state.current = item;
      document.getElementById("detailTitle").textContent = item.item_id;
      const stats = item.reference_outcomes;
      document.getElementById("detailBody").innerHTML = `
        ${item.thumbnail ? `<img class="detail-image" src="${esc(item.thumbnail)}" alt="${esc(item.content_label || item.relative_path)}">` : `<div class="state error">${esc(item.image_error || "Missing image")}</div>`}
        <div class="copy-actions"><button type="button" data-copy="id">复制 item ID</button><button type="button" data-copy="path">复制 source path</button><button type="button" data-copy="query" ${item.browse_query ? "" : "disabled"}>复制 browse query</button></div>
        <dl><dt>Domain</dt><dd>${esc(item.reference_domain)}</dd><dt>Source</dt><dd>${esc(item.source_label)} (${esc(item.source_id)})</dd><dt>Relative path</dt><dd>${esc(item.relative_path)}</dd><dt>Source path</dt><dd>${esc(item.source_path)}</dd><dt>Content hash</dt><dd>${esc(item.content_hash)}</dd><dt>Dimensions</dt><dd>${esc(item.width)} × ${esc(item.height)}</dd><dt>Subject forms</dt><dd>${esc(JSON.stringify(item.subject_forms))}</dd><dt>Shot / view</dt><dd>${esc([...(item.shot_types||[]),...(item.view_angles||[]).map(v=>`view:${v}`)].join(", ") || "—")}</dd><dt>Eligible roles</dt><dd>${esc((item.eligible_roles||[]).join(", ") || "—")}</dd><dt>Certified</dt><dd>${item.certified_style_anchor ? "yes" : "no"}</dd><dt>Outcomes</dt><dd>accepted ${stats.accepted}; rejected ${stats.rejected}; smoothed ${stats.smoothed_acceptance}; rank ${stats.feedback_rank}</dd></dl>
        <div><strong>Controlled tags</strong>${chips(item.tags||[])}</div>
        ${item.retrieval ? `<div><strong>Retrieval match reasons</strong>${chips(item.retrieval.match_reasons||[])}</div>` : ""}
        ${item.browse_query ? `<div><strong>Equivalent query</strong><pre>${esc(item.browse_query)}</pre></div>` : ""}`;
      document.getElementById("detail").showModal();
    }
    async function copyCurrent(kind) {
      const item = state.current; const value = kind === "id" ? item.item_id : kind === "path" ? item.source_path : item.browse_query;
      if (!value) return;
      try { await navigator.clipboard.writeText(value); document.getElementById("status").textContent = "已复制。"; }
      catch { const area = document.createElement("textarea"); area.value=value; document.body.append(area); area.select(); document.execCommand("copy"); area.remove(); }
    }
    document.getElementById("grid").addEventListener("click", event => { const button=event.target.closest("[data-detail]"); if (button) showDetail(state.byId.get(button.dataset.detail)); });
    document.getElementById("detailBody").addEventListener("click", event => { const button=event.target.closest("[data-copy]"); if (button) copyCurrent(button.dataset.copy); });
    document.getElementById("closeDetail").addEventListener("click", () => document.getElementById("detail").close());
    document.getElementById("detail").addEventListener("click", event => { if (event.target === event.currentTarget) event.currentTarget.close(); });
    for (const control of Object.values(controls)) control.addEventListener(control.type === "search" ? "input" : "change", render);
    document.getElementById("clear").addEventListener("click", () => { for (const control of Object.values(controls)) { if (control.type === "checkbox") control.checked=false; else control.value=""; } render(); controls.search.focus(); });
    fetch("references.json").then(response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); }).then(data => {
      if (!Array.isArray(data.items)) throw new Error("references.json 缺少 items 数组");
      state.items=data.items; state.byId=new Map(data.items.map(item=>[item.item_id,item])); state.queryContext=data.query_context;
      populate("subject",unique(data.items,"subjects")); populate("form",unique(data.items,"forms")); populate("shot",unique(data.items,"shot_types")); populate("view",unique(data.items,"view_angles")); populate("sceneId",unique(data.items,"scene_ids")); populate("sceneEconomy",unique(data.items,"scene_economy")); populate("blackMass",unique(data.items,"black_mass")); populate("tone",unique(data.items,"tone_density")); populate("falloff",unique(data.items,"detail_falloff")); populate("role",unique(data.items,"eligible_roles"));
      for (const control of Object.values(controls)) control.disabled=false; document.getElementById("clear").disabled=false; document.getElementById("loading").hidden=true;
      if (data.query_context) { document.getElementById("queryOnlyRow").hidden=false; document.getElementById("queryContext").textContent=`检索结果 ${data.query_result_count} 项`; }
      else controls.queryOnly.checked=false;
      const params=new URLSearchParams(location.search); for (const [id,control] of Object.entries(controls)) { if (!params.has(id) || (id === "queryOnly" && !data.query_context)) continue; if (control.type === "checkbox") control.checked=params.get(id)==="1"; else if ([...control.options].some(option=>option.value===params.get(id)) || id==="search") control.value=params.get(id); }
      render();
    }).catch(error => { document.getElementById("loading").hidden=true; const box=document.getElementById("error"); box.hidden=false; box.textContent=`无法读取 references.json：${error.message}。请用 builder 的 --serve 模式打开。`; document.getElementById("status").textContent="加载失败"; });
  </script>
</body>
</html>
'''


def build(config: dict, root: Path, query_results: Path | None) -> dict:
    gallery = root / "gallery"
    ensure_safe_output(gallery, config)
    gallery.mkdir(parents=True, exist_ok=True)
    payload = read_references(config, root, gallery, query_results)
    atomic_write_json(gallery / "references.json", payload)
    atomic_write_text(gallery / "index.html", HTML)
    serve_command = [
        "scripts/run-python",
        "scripts/build_workflow_gallery.py",
        "--workflow-root",
        str(root),
    ]
    if query_results is not None:
        serve_command += [
            "--query-results",
            str(query_results.expanduser().resolve()),
        ]
    serve_command.append("--serve")
    return {
        "gallery": str(gallery / "index.html"),
        "references": payload["count"],
        "thumbnail_errors": len(payload["errors"]),
        "query_results": payload["query_result_count"],
        "serve_command": shlex.join(serve_command),
    }


def serve(gallery: Path, port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(
        *args, directory=str(gallery), **kwargs
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"Serving http://127.0.0.1:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    args = parse_args()
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    try:
        result = build(config, root, args.query_results)
        print(
            json.dumps(result, ensure_ascii=False, indent=2)
            if args.json
            else result["gallery"]
        )
        if args.serve:
            serve(root / "gallery", args.port)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
