from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / ".codegraph" / "codegraph.db"
OUTPUT_PATH = ROOT / "docs" / "codegraph-starmap.html"

EXCLUDED_PREFIXES = (
    ".agents/",
    ".claude/",
    ".codex/",
    ".openclaw/",
    ".playwright-mcp/",
    "skills/",
    "frontend/node_modules/",
    "frontend/.next/",
    "frontend/.ruff_cache/",
    "frontend/test-results/",
    "backend/.venv/",
    "backend/.pytest_cache/",
    "backend/chroma_data/",
    "backend/uploads/",
)

EXCLUDED_PARTS = {
    "__pycache__",
    ".git",
    ".codegraph",
}

EDGE_KINDS = {"calls", "references", "imports", "instantiates", "extends"}

GROUP_COLORS = {
    "backend": "#ff8a65",
    "frontend": "#4fc3f7",
    "docs": "#81c784",
    "root": "#ffd54f",
    "other": "#ce93d8",
}


def include_file(file_path: str) -> bool:
    if not file_path:
        return False
    if any(file_path.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return False
    parts = file_path.split("/")
    if any(part in EXCLUDED_PARTS for part in parts):
        return False
    return True


def classify_module(file_path: str) -> str:
    parts = file_path.split("/")
    if len(parts) == 1:
        return "[root]"

    if parts[0] == "frontend":
        if len(parts) >= 3 and parts[1] == "src":
            return "/".join(parts[:3])
        if len(parts) >= 2:
            return "/".join(parts[: min(3, len(parts) - 1)])
        return "frontend"

    if parts[0] == "backend":
        if len(parts) >= 3 and parts[1] in {"app", "tests"}:
            return "/".join(parts[:3])
        if len(parts) >= 2 and parts[1] == "alembic":
            return "/".join(parts[:2])
        return "/".join(parts[: min(2, len(parts) - 1)])

    if parts[0] == "docs":
        return "/".join(parts[: min(3, len(parts) - 1)])

    return "/".join(parts[: min(2, len(parts) - 1)])


def top_group(module_id: str) -> str:
    if module_id.startswith("backend"):
        return "backend"
    if module_id.startswith("frontend"):
        return "frontend"
    if module_id.startswith("docs"):
        return "docs"
    if module_id == "[root]":
        return "root"
    return "other"


def radius_for_size(value: int, minimum: float, scale: float) -> float:
    return round(minimum + math.sqrt(max(value, 1)) * scale, 2)


def load_data() -> dict[str, Any]:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"CodeGraph database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    file_rows = cur.execute(
        """
        select file_path, language
        from nodes
        where kind = 'file'
        order by file_path
        """
    ).fetchall()

    source_files: dict[str, dict[str, Any]] = {}
    for row in file_rows:
        file_path = row["file_path"]
        if not include_file(file_path):
            continue
        source_files[file_path] = {
            "filePath": file_path,
            "language": row["language"],
            "module": classify_module(file_path),
        }

    symbol_rows = cur.execute(
        """
        select file_path, kind, count(*) as total
        from nodes
        where kind != 'file'
        group by file_path, kind
        """
    ).fetchall()

    for row in symbol_rows:
        file_path = row["file_path"]
        if file_path not in source_files:
            continue
        info = source_files[file_path]
        info.setdefault("symbolCount", 0)
        info.setdefault("kindBreakdown", {})
        info["symbolCount"] += row["total"]
        info["kindBreakdown"][row["kind"]] = row["total"]

    edge_rows = cur.execute(
        """
        select s.file_path as source_path,
               t.file_path as target_path,
               e.kind as edge_kind,
               count(*) as total
        from edges e
        join nodes s on s.id = e.source
        join nodes t on t.id = e.target
        where e.kind in ('calls', 'references', 'imports', 'instantiates', 'extends')
        group by source_path, target_path, edge_kind
        """
    ).fetchall()
    conn.close()

    module_nodes: dict[str, dict[str, Any]] = {}
    detail_nodes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    module_languages: dict[str, Counter[str]] = defaultdict(Counter)

    for file_path, info in source_files.items():
        module_id = info["module"]
        module = module_nodes.setdefault(
            module_id,
            {
                "id": module_id,
                "label": module_id.split("/")[-1] if module_id != "[root]" else "[root]",
                "modulePath": module_id,
                "group": top_group(module_id),
                "color": GROUP_COLORS[top_group(module_id)],
                "fileCount": 0,
                "symbolCount": 0,
                "kindBreakdown": Counter(),
                "languages": Counter(),
            },
        )
        module["fileCount"] += 1
        module["symbolCount"] += info.get("symbolCount", 0)
        module["kindBreakdown"].update(info.get("kindBreakdown", {}))
        module["languages"][info["language"]] += 1
        detail_nodes[module_id].append(
            {
                "id": file_path,
                "label": Path(file_path).name,
                "filePath": file_path,
                "language": info["language"],
                "symbolCount": info.get("symbolCount", 0),
                "kindBreakdown": info.get("kindBreakdown", {}),
            }
        )
        module_languages[module_id][info["language"]] += 1

    module_edge_weights: dict[tuple[str, str], int] = defaultdict(int)
    detail_edge_weights: dict[str, dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))
    external_file_weights: Counter[str] = Counter()

    for row in edge_rows:
        source_path = row["source_path"]
        target_path = row["target_path"]
        if source_path not in source_files or target_path not in source_files:
            continue
        if source_path == target_path:
            continue

        source_module = source_files[source_path]["module"]
        target_module = source_files[target_path]["module"]
        weight = int(row["total"])

        module_pair = tuple(sorted((source_module, target_module)))
        module_edge_weights[module_pair] += weight

        if source_module == target_module:
            file_pair = tuple(sorted((source_path, target_path)))
            detail_edge_weights[source_module][file_pair] += weight
        else:
            external_file_weights[source_path] += weight
            external_file_weights[target_path] += weight

    overview_nodes = []
    for module in module_nodes.values():
        dominant_language = module["languages"].most_common(1)[0][0] if module["languages"] else "unknown"
        overview_nodes.append(
            {
                "id": module["id"],
                "label": module["label"],
                "modulePath": module["modulePath"],
                "group": module["group"],
                "color": module["color"],
                "fileCount": module["fileCount"],
                "symbolCount": module["symbolCount"],
                "language": dominant_language,
                "kindBreakdown": dict(module["kindBreakdown"]),
                "radius": radius_for_size(module["symbolCount"], minimum=14, scale=1.15),
            }
        )

    module_degree: Counter[str] = Counter()
    overview_edges = []
    for (source_module, target_module), weight in module_edge_weights.items():
        module_degree[source_module] += weight
        module_degree[target_module] += weight
        overview_edges.append(
            {
                "source": source_module,
                "target": target_module,
                "weight": weight,
            }
        )

    for node in overview_nodes:
        node["degree"] = module_degree[node["id"]]

    detail_graphs: dict[str, Any] = {}
    for module_id, files in detail_nodes.items():
        files.sort(key=lambda item: (-item["symbolCount"], item["label"]))
        file_degree: Counter[str] = Counter()
        edges = []
        for (source_file, target_file), weight in detail_edge_weights[module_id].items():
            file_degree[source_file] += weight
            file_degree[target_file] += weight
            edges.append(
                {
                    "source": source_file,
                    "target": target_file,
                    "weight": weight,
                }
            )

        detail_graphs[module_id] = {
            "title": module_id,
            "nodes": [
                {
                    **item,
                    "radius": radius_for_size(item["symbolCount"], minimum=10, scale=0.9),
                    "externalWeight": external_file_weights[item["id"]],
                    "degree": file_degree[item["id"]],
                    "color": GROUP_COLORS[top_group(module_id)],
                }
                for item in files
            ],
            "edges": edges,
        }

    included_files = sum(node["fileCount"] for node in overview_nodes)
    included_symbols = sum(node["symbolCount"] for node in overview_nodes)

    return {
        "project": "ai-agent",
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "sourceScope": {
            "includedFiles": included_files,
            "includedSymbols": included_symbols,
            "excludedPrefixes": list(EXCLUDED_PREFIXES),
        },
        "overview": {
            "nodes": sorted(overview_nodes, key=lambda node: (-node["symbolCount"], node["modulePath"])),
            "edges": sorted(overview_edges, key=lambda edge: -edge["weight"]),
        },
        "details": detail_graphs,
    }


def build_html(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    color_map = json.dumps(GROUP_COLORS, ensure_ascii=False)
    template = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__PROJECT__ CodeGraph 星图</title>
  <style>
    :root {
      --space-0: #030712;
      --space-1: #07101d;
      --space-2: #0b1830;
      --space-3: #102545;
      --panel-bg: rgba(7, 13, 24, 0.82);
      --panel-bg-strong: rgba(9, 17, 30, 0.94);
      --panel-line: rgba(135, 180, 255, 0.16);
      --panel-line-strong: rgba(135, 180, 255, 0.28);
      --text-0: #f4f7ff;
      --text-1: rgba(230, 238, 255, 0.74);
      --text-2: rgba(184, 198, 230, 0.5);
      --accent: #91d7ff;
      --accent-warm: #ffd47a;
      --shadow: 0 20px 60px rgba(0, 0, 0, 0.42);
    }

    * {
      box-sizing: border-box;
    }

    html,
    body {
      min-height: 100%;
    }

    body {
      margin: 0;
      overflow: hidden;
      color: var(--text-0);
      font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 18% 18%, rgba(87, 138, 255, 0.16), transparent 24%),
        radial-gradient(circle at 70% 14%, rgba(77, 196, 255, 0.12), transparent 22%),
        radial-gradient(circle at 82% 76%, rgba(118, 81, 255, 0.12), transparent 24%),
        linear-gradient(180deg, #050913 0%, #07101d 38%, #03060d 100%);
    }

    body::before,
    body::after {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
    }

    body::before {
      background:
        radial-gradient(circle at 24% 28%, rgba(94, 151, 255, 0.16), transparent 0 18%),
        radial-gradient(circle at 76% 22%, rgba(64, 230, 255, 0.13), transparent 0 16%),
        radial-gradient(circle at 58% 74%, rgba(132, 92, 255, 0.12), transparent 0 14%);
      filter: blur(48px) saturate(118%);
      opacity: 0.9;
    }

    body::after {
      background:
        linear-gradient(transparent 0%, rgba(255, 255, 255, 0.03) 50%, transparent 100%);
      background-size: 100% 4px;
      opacity: 0.06;
      mix-blend-mode: screen;
    }

    #app {
      position: relative;
      display: grid;
      grid-template-columns: minmax(340px, 390px) 1fr;
      min-height: 100vh;
    }

    aside {
      position: relative;
      z-index: 4;
      padding: 24px;
      overflow-y: auto;
      background:
        linear-gradient(180deg, rgba(10, 18, 31, 0.96) 0%, rgba(8, 14, 24, 0.9) 100%);
      border-right: 1px solid rgba(152, 190, 255, 0.14);
      box-shadow: 28px 0 80px rgba(2, 6, 16, 0.58);
      backdrop-filter: blur(22px);
    }

    aside::before {
      content: "";
      position: absolute;
      inset: 14px 14px 14px 14px;
      border: 1px solid rgba(145, 215, 255, 0.08);
      border-radius: 28px;
      pointer-events: none;
    }

    main {
      position: relative;
      overflow: hidden;
      background:
        radial-gradient(circle at 50% 44%, rgba(30, 61, 106, 0.2), transparent 0 28%),
        radial-gradient(circle at 62% 56%, rgba(50, 107, 164, 0.16), transparent 0 24%);
    }

    #map {
      display: block;
      width: 100%;
      height: 100vh;
    }

    .shell {
      position: relative;
      display: grid;
      gap: 16px;
      z-index: 1;
    }

    .kicker {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      color: var(--accent);
      font-size: 11px;
      letter-spacing: 0.24em;
      text-transform: uppercase;
    }

    .kicker::before,
    .kicker::after {
      content: "";
      height: 1px;
      width: 32px;
      background: linear-gradient(90deg, transparent, rgba(145, 215, 255, 0.65), transparent);
    }

    h1 {
      margin: 0;
      font-size: 31px;
      line-height: 1.08;
      letter-spacing: 0.01em;
      text-wrap: balance;
    }

    p {
      margin: 0;
      color: var(--text-1);
      line-height: 1.72;
      font-size: 14px;
    }

    .lead {
      max-width: 32ch;
    }

    .panel {
      position: relative;
      padding: 16px;
      border-radius: 22px;
      border: 1px solid var(--panel-line);
      background:
        linear-gradient(180deg, rgba(16, 28, 46, 0.54), rgba(8, 15, 24, 0.72)),
        var(--panel-bg);
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .panel::before {
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(120deg, rgba(255, 255, 255, 0.06), transparent 26%),
        linear-gradient(180deg, rgba(145, 215, 255, 0.08), transparent 36%);
      pointer-events: none;
    }

    .panel-header {
      position: relative;
      z-index: 1;
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 14px;
    }

    .panel-title {
      font-size: 13px;
      font-weight: 600;
      color: var(--text-0);
      letter-spacing: 0.05em;
    }

    .panel-meta {
      color: var(--text-2);
      font-size: 11px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }

    .stats {
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .stat {
      padding: 13px 12px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(145, 215, 255, 0.08);
    }

    .stat strong {
      display: block;
      font-size: 21px;
      line-height: 1.1;
      color: var(--text-0);
    }

    .stat span {
      display: block;
      margin-top: 5px;
      font-size: 12px;
      color: var(--text-1);
    }

    .button-row {
      position: relative;
      z-index: 1;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    button {
      appearance: none;
      border: 1px solid rgba(145, 215, 255, 0.18);
      background:
        linear-gradient(180deg, rgba(146, 214, 255, 0.14), rgba(146, 214, 255, 0.06));
      color: var(--text-0);
      border-radius: 999px;
      padding: 10px 14px;
      font: inherit;
      font-size: 13px;
      cursor: pointer;
      transition: transform 160ms ease, border-color 160ms ease, background 160ms ease, box-shadow 160ms ease;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
    }

    button:hover {
      transform: translateY(-1px);
      border-color: rgba(145, 215, 255, 0.34);
      background:
        linear-gradient(180deg, rgba(146, 214, 255, 0.2), rgba(146, 214, 255, 0.1));
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.12),
        0 0 0 1px rgba(145, 215, 255, 0.08),
        0 12px 28px rgba(27, 85, 144, 0.2);
    }

    button[hidden] {
      display: none;
    }

    .legend {
      position: relative;
      z-index: 1;
      display: grid;
      gap: 8px;
    }

    .legend-item {
      display: grid;
      grid-template-columns: 12px 1fr auto;
      align-items: center;
      gap: 10px;
      padding: 8px 0;
      color: var(--text-1);
      font-size: 13px;
      border-bottom: 1px solid rgba(145, 215, 255, 0.06);
    }

    .legend-item:last-child {
      border-bottom: 0;
    }

    .swatch,
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      box-shadow: 0 0 16px currentColor;
    }

    .legend-note {
      color: var(--text-2);
      font-size: 11px;
      letter-spacing: 0.08em;
    }

    .detail-stack {
      display: grid;
      gap: 14px;
    }

    .detail-card {
      position: relative;
      overflow: hidden;
      padding: 16px;
      border-radius: 20px;
      border: 1px solid rgba(145, 215, 255, 0.12);
      background:
        radial-gradient(circle at top right, rgba(145, 215, 255, 0.12), transparent 38%),
        linear-gradient(180deg, rgba(15, 23, 39, 0.78), rgba(9, 15, 27, 0.9));
      box-shadow: var(--shadow);
    }

    .detail-card::before {
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(90deg, rgba(145, 215, 255, 0.08), transparent 22%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent 18%);
      pointer-events: none;
    }

    .detail-title {
      position: relative;
      z-index: 1;
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
      font-size: 18px;
      font-weight: 600;
      line-height: 1.25;
    }

    .detail-path {
      position: relative;
      z-index: 1;
      margin-bottom: 12px;
      color: var(--text-2);
      font-size: 12px;
      line-height: 1.5;
      word-break: break-all;
    }

    .list {
      position: relative;
      z-index: 1;
      display: grid;
      gap: 8px;
    }

    .list-item {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      color: var(--text-1);
      font-size: 13px;
    }

    .list-item strong {
      color: var(--text-0);
      font-weight: 600;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }

    .chips {
      position: relative;
      z-index: 1;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .chip {
      padding: 7px 10px;
      border-radius: 999px;
      border: 1px solid rgba(145, 215, 255, 0.14);
      background: rgba(255, 255, 255, 0.03);
      color: var(--text-1);
      font-size: 12px;
    }

    .hud {
      position: absolute;
      inset: 20px 22px auto auto;
      z-index: 3;
      display: grid;
      gap: 10px;
      width: min(360px, calc(100% - 44px));
      pointer-events: none;
    }

    .hud-card {
      padding: 14px 16px;
      border-radius: 18px;
      border: 1px solid rgba(145, 215, 255, 0.16);
      background:
        linear-gradient(180deg, rgba(9, 19, 35, 0.7), rgba(5, 10, 19, 0.82));
      backdrop-filter: blur(16px);
      box-shadow: 0 18px 40px rgba(3, 8, 18, 0.42);
    }

    .hud-top {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      color: var(--text-1);
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .hud-strong {
      color: var(--text-0);
      font-size: 15px;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: none;
    }

    .hud-sub {
      margin-top: 10px;
      color: var(--text-1);
      font-size: 13px;
      line-height: 1.6;
    }

    .hint {
      position: absolute;
      left: 24px;
      right: 24px;
      bottom: 20px;
      z-index: 3;
      display: flex;
      justify-content: center;
      pointer-events: none;
    }

    .hint-pill {
      padding: 10px 16px;
      border-radius: 999px;
      border: 1px solid rgba(145, 215, 255, 0.16);
      background: rgba(4, 9, 18, 0.56);
      color: rgba(225, 235, 255, 0.8);
      font-size: 12px;
      letter-spacing: 0.04em;
      backdrop-filter: blur(12px);
    }

    .empty {
      color: var(--text-1);
      font-size: 13px;
      line-height: 1.7;
    }

    .empty strong {
      display: block;
      margin-bottom: 6px;
      color: var(--text-0);
      font-size: 16px;
    }

    @media (max-width: 1120px) {
      #app {
        grid-template-columns: minmax(320px, 360px) 1fr;
      }
    }

    @media (max-width: 980px) {
      body {
        overflow: auto;
      }

      #app {
        grid-template-columns: 1fr;
      }

      aside {
        border-right: 0;
        border-bottom: 1px solid rgba(152, 190, 255, 0.12);
      }

      #map {
        height: 68vh;
      }

      .hud {
        inset: 16px 16px auto 16px;
        width: auto;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation: none !important;
        transition: none !important;
        scroll-behavior: auto !important;
      }
    }
  </style>
</head>
<body>
  <div id="app">
    <aside>
      <div class="shell">
        <div class="kicker">CodeGraph Deep Space</div>
        <div>
          <h1>源码宇宙星图</h1>
          <p class="lead" id="subtitle">把项目结构映射成可探索的星系视图，既保留依赖关系的可读性，也让它更像一张真实的深空导航图。</p>
        </div>

        <section class="panel">
          <div class="panel-header">
            <div class="panel-title">星域总览</div>
            <div class="panel-meta" id="viewMode">overview</div>
          </div>
          <div class="stats">
            <div class="stat"><strong id="stat-modules">0</strong><span>模块星系</span></div>
            <div class="stat"><strong id="stat-links">0</strong><span>引力航迹</span></div>
            <div class="stat"><strong id="stat-files">0</strong><span>纳入文件</span></div>
            <div class="stat"><strong id="stat-symbols">0</strong><span>纳入符号</span></div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <div class="panel-title">导航控制</div>
            <div class="panel-meta">bridge</div>
          </div>
          <div class="button-row">
            <button id="backButton" hidden>返回概览</button>
            <button id="recenterButton">重置星图</button>
          </div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <div class="panel-title">星系图例</div>
            <div class="panel-meta">clusters</div>
          </div>
          <div class="legend" id="legend"></div>
        </section>

        <section>
          <div id="detail" class="detail-stack"></div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <div class="panel-title">过滤范围</div>
            <div class="panel-meta">noise off</div>
          </div>
          <div class="chips" id="filters"></div>
        </section>
      </div>
    </aside>

    <main>
      <canvas id="map"></canvas>

      <div class="hud">
        <div class="hud-card">
          <div class="hud-top">
            <span>__PROJECT__</span>
            <span class="hud-strong" id="hudMode">模块概览</span>
          </div>
          <div class="hud-sub" id="hudSub">每颗恒星代表一个模块，亮度和尺寸对应代码规模，弧形光迹对应依赖与引用强度。</div>
        </div>
        <div class="hud-card">
          <div class="hud-top">
            <span>扫描时间</span>
            <span id="hudTimestamp">__GENERATED_AT__</span>
          </div>
        </div>
      </div>

      <div class="hint">
        <div class="hint-pill">悬停查看星体摘要，单击锁定，概览层单击即可下钻到文件层。</div>
      </div>
    </main>
  </div>

  <script id="graph-data" type="application/json">__PAYLOAD__</script>
  <script>
    const data = JSON.parse(document.getElementById("graph-data").textContent);
    const colorMap = __COLOR_MAP__;
    const colorLabels = {
      backend: "后端",
      frontend: "前端",
      docs: "文档",
      root: "根目录",
      other: "其他"
    };

    const canvas = document.getElementById("map");
    const ctx = canvas.getContext("2d");
    const detailEl = document.getElementById("detail");
    const backButton = document.getElementById("backButton");
    const recenterButton = document.getElementById("recenterButton");
    const subtitle = document.getElementById("subtitle");
    const viewMode = document.getElementById("viewMode");
    const hudMode = document.getElementById("hudMode");
    const hudSub = document.getElementById("hudSub");
    const hudTimestamp = document.getElementById("hudTimestamp");
    const legend = document.getElementById("legend");
    const filters = document.getElementById("filters");
    const stats = {
      modules: document.getElementById("stat-modules"),
      links: document.getElementById("stat-links"),
      files: document.getElementById("stat-files"),
      symbols: document.getElementById("stat-symbols")
    };

    const starfieldFar = Array.from({ length: 420 }, () => ({
      x: Math.random(),
      y: Math.random(),
      size: Math.random() * 1.05 + 0.18,
      alpha: Math.random() * 0.32 + 0.06,
      drift: Math.random() * 0.00008 + 0.00002
    }));
    const starfieldNear = Array.from({ length: 64 }, () => ({
      x: Math.random(),
      y: Math.random(),
      size: Math.random() * 1.2 + 0.5,
      alpha: Math.random() * 0.26 + 0.12,
      hue: Math.random() > 0.8 ? "warm" : "cool"
    }));
    const nebulae = [
      { x: 0.2, y: 0.26, radius: 0.28, color: "rgba(88, 132, 255, 0.18)" },
      { x: 0.72, y: 0.18, radius: 0.2, color: "rgba(65, 223, 255, 0.12)" },
      { x: 0.68, y: 0.72, radius: 0.24, color: "rgba(120, 90, 255, 0.12)" },
      { x: 0.42, y: 0.54, radius: 0.32, color: "rgba(20, 70, 118, 0.14)" }
    ];
    const dustLanes = Array.from({ length: 36 }, (_, index) => ({
      angle: (Math.PI * 2 * index) / 36,
      spread: 0.24 + (index % 5) * 0.04,
      width: 0.08 + (index % 3) * 0.018,
      alpha: 0.025 + (index % 4) * 0.01
    }));

    Object.entries(colorMap).forEach(([key, color]) => {
      const row = document.createElement("div");
      row.className = "legend-item";
      row.innerHTML = `<span class="swatch" style="color:${color}; background:${color}"></span><span>${colorLabels[key] || key}</span><span class="legend-note">${key}</span>`;
      legend.appendChild(row);
    });

    data.sourceScope.excludedPrefixes.forEach((value) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = value;
      filters.appendChild(chip);
    });

    function cloneGraph(graph) {
      return {
        nodes: graph.nodes.map((node) => ({
          ...node,
          x: 0,
          y: 0,
          vx: 0,
          vy: 0
        })),
        edges: graph.edges.map((edge) => ({ ...edge }))
      };
    }

    function buildView(name, graph, meta) {
      return {
        name,
        graph: cloneGraph(graph),
        meta,
        selectedId: null
      };
    }

    const overview = buildView("overview", data.overview, {
      title: "模块星系概览",
      subtitle: "每颗恒星代表一个源码模块，体量越大，星体越亮。"
    });

    const details = Object.fromEntries(
      Object.entries(data.details).map(([key, graph]) => [key, buildView(key, graph, {
        title: key,
        subtitle: "文件层视图，仅展示当前模块内部的依赖航迹。"
      })])
    );

    let currentView = overview;
    let hoveredNode = null;
    let pointer = { x: 0, y: 0 };
    let deviceScale = Math.max(window.devicePixelRatio || 1, 1);
    let tick = 0;

    function formatNumber(value) {
      return (value || 0).toLocaleString("zh-CN");
    }

    function resizeCanvas() {
      deviceScale = Math.max(window.devicePixelRatio || 1, 1);
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.floor(rect.width * deviceScale);
      canvas.height = Math.floor(rect.height * deviceScale);
      ctx.setTransform(deviceScale, 0, 0, deviceScale, 0, 0);
      seedLayout(currentView);
    }

    function seedLayout(view) {
      const rect = canvas.getBoundingClientRect();
      const nodes = view.graph.nodes;
      const centerX = rect.width * 0.54;
      const centerY = rect.height * 0.5;
      const ring = Math.min(rect.width, rect.height) * (view === overview ? 0.31 : 0.24);
      nodes.forEach((node, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1);
        const wobble = 0.58 + (index % 6) * 0.075 + Math.random() * 0.06;
        node.x = centerX + Math.cos(angle) * ring * wobble;
        node.y = centerY + Math.sin(angle) * ring * (0.82 + Math.random() * 0.14);
        node.vx = 0;
        node.vy = 0;
      });
    }

    function graphStats(view) {
      if (view === overview) {
        return {
          modules: view.graph.nodes.length,
          links: view.graph.edges.length,
          files: data.sourceScope.includedFiles,
          symbols: data.sourceScope.includedSymbols
        };
      }

      const files = view.graph.nodes.length;
      const symbols = view.graph.nodes.reduce((sum, node) => sum + (node.symbolCount || 0), 0);
      return {
        modules: files,
        links: view.graph.edges.length,
        files,
        symbols
      };
    }

    function getSelectedNode() {
      return currentView.graph.nodes.find((node) => node.id === currentView.selectedId) || hoveredNode;
    }

    function renderEmptyState() {
      detailEl.innerHTML = `
        <div class="detail-card">
          <div class="empty">
            <strong>等待锁定目标</strong>
            把光标移到星体上即可查看摘要，单击后会保持当前目标。模块概览层继续单击可以进入该模块的文件星系。
          </div>
        </div>
      `;
    }

    function updateSidebar() {
      const numbers = graphStats(currentView);
      const selected = getSelectedNode();

      stats.modules.textContent = formatNumber(numbers.modules);
      stats.links.textContent = formatNumber(numbers.links);
      stats.files.textContent = formatNumber(numbers.files);
      stats.symbols.textContent = formatNumber(numbers.symbols);

      subtitle.textContent = currentView.meta.subtitle;
      viewMode.textContent = currentView === overview ? "overview" : "detail";
      hudMode.textContent = currentView === overview ? "模块概览" : "文件下钻";
      hudSub.textContent = currentView === overview
        ? "观察模块之间的依赖航迹与代码密度，识别真正的核心星系。"
        : "当前处于文件层，星体间连线仅保留模块内部关系，便于看清局部结构。";
      hudTimestamp.textContent = data.generatedAt;
      backButton.hidden = currentView === overview;

      if (!selected) {
        renderEmptyState();
        return;
      }

      const groupColor = selected.color || colorMap[selected.group] || "#91d7ff";
      const breakdown = Object.entries(selected.kindBreakdown || {})
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([kind, total]) => `<div class="list-item"><strong>${kind}</strong><span>${formatNumber(total)}</span></div>`)
        .join("");

      const pathLine = currentView === overview ? selected.modulePath : selected.filePath;
      const rows = currentView === overview
        ? `
          <div class="list-item"><strong>文件数量</strong><span>${formatNumber(selected.fileCount)}</span></div>
          <div class="list-item"><strong>主语言</strong><span>${selected.language || "unknown"}</span></div>
          <div class="list-item"><strong>关联强度</strong><span>${formatNumber(selected.degree)}</span></div>
          <div class="list-item"><strong>符号规模</strong><span>${formatNumber(selected.symbolCount)}</span></div>
        `
        : `
          <div class="list-item"><strong>语言</strong><span>${selected.language || "unknown"}</span></div>
          <div class="list-item"><strong>外部关联</strong><span>${formatNumber(selected.externalWeight)}</span></div>
          <div class="list-item"><strong>内部关联</strong><span>${formatNumber(selected.degree)}</span></div>
          <div class="list-item"><strong>符号规模</strong><span>${formatNumber(selected.symbolCount)}</span></div>
        `;

      detailEl.innerHTML = `
        <div class="detail-card">
          <div class="detail-title">
            <span class="dot" style="color:${groupColor}; background:${groupColor}"></span>
            <span>${selected.label}</span>
          </div>
          <div class="detail-path">${pathLine}</div>
          <div class="list">${rows}</div>
        </div>
        <div class="detail-card">
          <div class="detail-title">
            <span class="dot" style="color:${groupColor}; background:${groupColor}"></span>
            <span>主要构成</span>
          </div>
          <div class="list">${breakdown || '<div class="empty">没有更多统计。</div>'}</div>
        </div>
      `;
    }

    function stepSimulation() {
      const rect = canvas.getBoundingClientRect();
      const nodes = currentView.graph.nodes;
      const edges = currentView.graph.edges;
      const centerX = rect.width * 0.54;
      const centerY = rect.height * 0.5;
      const byId = Object.fromEntries(nodes.map((node) => [node.id, node]));

      for (let i = 0; i < nodes.length; i += 1) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j += 1) {
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const distSq = dx * dx + dy * dy + 0.01;
          const dist = Math.sqrt(distSq);
          const force = (currentView === overview ? 2100 : 1600) / distSq;
          a.vx += (dx / dist) * force;
          a.vy += (dy / dist) * force;
          b.vx -= (dx / dist) * force;
          b.vy -= (dy / dist) * force;
        }
      }

      for (const edge of edges) {
        const source = byId[edge.source];
        const target = byId[edge.target];
        if (!source || !target) continue;
        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const dist = Math.sqrt(dx * dx + dy * dy) + 0.001;
        const desired = currentView === overview ? 152 : 100;
        const spring = (currentView === overview ? 0.00125 : 0.0015) * Math.min(edge.weight, 48);
        const offset = (dist - desired) * spring;
        source.vx += (dx / dist) * offset;
        source.vy += (dy / dist) * offset;
        target.vx -= (dx / dist) * offset;
        target.vy -= (dy / dist) * offset;
      }

      for (const node of nodes) {
        const orbitPull = currentView === overview ? 0.00052 : 0.0007;
        node.vx += (centerX - node.x) * orbitPull;
        node.vy += (centerY - node.y) * orbitPull;

        node.vx *= currentView === overview ? 0.84 : 0.82;
        node.vy *= currentView === overview ? 0.84 : 0.82;

        const speed = Math.sqrt(node.vx * node.vx + node.vy * node.vy);
        const maxSpeed = currentView === overview ? 5.8 : 4.6;
        if (speed > maxSpeed) {
          node.vx = (node.vx / speed) * maxSpeed;
          node.vy = (node.vy / speed) * maxSpeed;
        }

        node.x += node.vx;
        node.y += node.vy;
      }
    }

    function drawNebula(width, height, x, y, radius, color) {
      const gradient = ctx.createRadialGradient(
        width * x,
        height * y,
        0,
        width * x,
        height * y,
        Math.max(width, height) * radius
      );
      gradient.addColorStop(0, color);
      gradient.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.rect(0, 0, width, height);
      ctx.fill();
    }

    function drawBackground(width, height) {
      const base = ctx.createLinearGradient(0, 0, 0, height);
      base.addColorStop(0, "#040914");
      base.addColorStop(0.4, "#07111f");
      base.addColorStop(1, "#02050b");
      ctx.fillStyle = base;
      ctx.fillRect(0, 0, width, height);

      nebulae.forEach((cloud) => drawNebula(width, height, cloud.x, cloud.y, cloud.radius, cloud.color));

      const systemCenterX = width * 0.54;
      const systemCenterY = height * 0.5;
      const pulse = (Math.sin(tick * 0.0012) + 1) * 0.5;

      ctx.save();
      ctx.translate(systemCenterX, systemCenterY);
      ctx.strokeStyle = "rgba(142, 203, 255, 0.08)";
      ctx.lineWidth = 1;
      for (let i = 1; i <= 5; i += 1) {
        ctx.beginPath();
        ctx.ellipse(0, 0, width * (0.12 + i * 0.08), height * (0.08 + i * 0.05), 0, 0, Math.PI * 2);
        ctx.stroke();
      }

      ctx.strokeStyle = "rgba(255, 211, 122, 0.08)";
      ctx.lineWidth = 1.2;
      for (const lane of dustLanes) {
        ctx.beginPath();
        ctx.arc(
          0,
          0,
          Math.min(width, height) * (0.18 + lane.spread),
          lane.angle + pulse * 0.1,
          lane.angle + lane.width + pulse * 0.1
        );
        ctx.stroke();
      }

      ctx.rotate(tick * 0.00008);
      const sweep = ctx.createRadialGradient(0, 0, 0, 0, 0, Math.max(width, height) * 0.72);
      sweep.addColorStop(0, "rgba(145, 215, 255, 0.08)");
      sweep.addColorStop(0.32, "rgba(145, 215, 255, 0.035)");
      sweep.addColorStop(1, "rgba(145, 215, 255, 0)");
      ctx.fillStyle = sweep;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, Math.max(width, height) * 0.72, -0.08, 0.08);
      ctx.closePath();
      ctx.fill();
      ctx.restore();

      for (const star of starfieldFar) {
        const twinkle = 0.72 + Math.sin(tick * star.drift * 1000 + star.x * 19) * 0.28;
        ctx.globalAlpha = star.alpha * twinkle;
        ctx.fillStyle = "#f5fbff";
        ctx.beginPath();
        ctx.arc(star.x * width, star.y * height, star.size, 0, Math.PI * 2);
        ctx.fill();
      }

      for (const star of starfieldNear) {
        const x = star.x * width;
        const y = star.y * height;
        const hueColor = star.hue === "warm" ? "rgba(255, 216, 162, 0.9)" : "rgba(216, 238, 255, 0.96)";
        const glow = ctx.createRadialGradient(x, y, 0, x, y, star.size * 7);
        glow.addColorStop(0, hueColor);
        glow.addColorStop(1, "rgba(255,255,255,0)");
        ctx.globalAlpha = star.alpha;
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(x, y, star.size * 6, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = star.hue === "warm" ? "#ffe2a6" : "#ffffff";
        ctx.beginPath();
        ctx.arc(x, y, star.size, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.globalAlpha = 1;

      const vignette = ctx.createRadialGradient(width * 0.54, height * 0.5, Math.min(width, height) * 0.12, width * 0.54, height * 0.5, Math.max(width, height) * 0.74);
      vignette.addColorStop(0, "rgba(0,0,0,0)");
      vignette.addColorStop(1, "rgba(0,0,0,0.42)");
      ctx.fillStyle = vignette;
      ctx.fillRect(0, 0, width, height);
    }

    function drawEdge(source, target, edge) {
      const active = source.id === currentView.selectedId || target.id === currentView.selectedId || source === hoveredNode || target === hoveredNode;
      const mx = (source.x + target.x) / 2;
      const my = (source.y + target.y) / 2;
      const curve = currentView === overview ? 30 : 18;
      const gradient = ctx.createLinearGradient(source.x, source.y, target.x, target.y);
      gradient.addColorStop(0, `${source.color}12`);
      gradient.addColorStop(0.48, active ? "rgba(172, 229, 255, 0.56)" : "rgba(145, 215, 255, 0.2)");
      gradient.addColorStop(1, `${target.color}12`);

      ctx.strokeStyle = gradient;
      ctx.lineWidth = (active ? 0.9 : 0.5) + Math.min(edge.weight, 32) * 0.045;
      ctx.shadowBlur = active ? 18 : 10;
      ctx.shadowColor = active ? "rgba(145, 215, 255, 0.45)" : "rgba(91, 162, 255, 0.18)";
      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.quadraticCurveTo(mx, my - curve, target.x, target.y);
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    function drawNode(node) {
      const active = node.id === currentView.selectedId || node === hoveredNode;
      const radius = node.radius + (active ? 2.2 : 0);
      const halo = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, radius * (active ? 4.7 : 3.5));
      halo.addColorStop(0, `${node.color}${active ? "dd" : "ad"}`);
      halo.addColorStop(0.34, `${node.color}30`);
      halo.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius * (active ? 4.1 : 3.2), 0, Math.PI * 2);
      ctx.fill();

      if (active) {
        ctx.strokeStyle = "rgba(201, 236, 255, 0.72)";
        ctx.lineWidth = 1.1;
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius * 1.7, 0, Math.PI * 2);
        ctx.stroke();
      }

      const core = ctx.createRadialGradient(node.x - radius * 0.3, node.y - radius * 0.3, 0, node.x, node.y, radius * 1.4);
      core.addColorStop(0, "rgba(255,255,255,0.98)");
      core.addColorStop(0.25, `${node.color}f2`);
      core.addColorStop(1, `${node.color}b2`);
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = active ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.18)";
      ctx.lineWidth = active ? 1.5 : 0.9;
      ctx.stroke();

      const shouldLabel = active || node.radius >= (currentView === overview ? 20 : 15);
      if (!shouldLabel) {
        return;
      }

      const labelY = node.y - radius - 14;
      const labelWidth = Math.max(56, ctx.measureText(node.label).width + 18);
      ctx.save();
      ctx.font = active ? '600 13px "Segoe UI", sans-serif' : '12px "Segoe UI", sans-serif';
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      ctx.fillStyle = active ? "rgba(7, 13, 24, 0.82)" : "rgba(5, 10, 18, 0.62)";
      ctx.strokeStyle = active ? "rgba(189, 230, 255, 0.28)" : "rgba(145, 215, 255, 0.08)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(node.x - labelWidth / 2, labelY - 10, labelWidth, 20, 999);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = active ? "rgba(255,255,255,0.98)" : "rgba(226,236,255,0.82)";
      ctx.fillText(node.label, node.x, labelY);
      ctx.restore();
    }

    function drawGraph() {
      const rect = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, rect.width, rect.height);
      drawBackground(rect.width, rect.height);

      const nodes = currentView.graph.nodes;
      const edges = currentView.graph.edges;
      const byId = Object.fromEntries(nodes.map((node) => [node.id, node]));

      for (const edge of edges) {
        const source = byId[edge.source];
        const target = byId[edge.target];
        if (!source || !target) continue;
        drawEdge(source, target, edge);
      }

      nodes
        .slice()
        .sort((a, b) => a.radius - b.radius)
        .forEach((node) => drawNode(node));
    }

    function pickNode(x, y) {
      let match = null;
      let bestDistance = Infinity;
      for (const node of currentView.graph.nodes) {
        const dx = x - node.x;
        const dy = y - node.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        if (distance <= node.radius + 7 && distance < bestDistance) {
          match = node;
          bestDistance = distance;
        }
      }
      return match;
    }

    function switchView(view) {
      currentView = view;
      hoveredNode = null;
      currentView.selectedId = null;
      seedLayout(currentView);
      updateSidebar();
    }

    canvas.addEventListener("mousemove", (event) => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = event.clientX - rect.left;
      pointer.y = event.clientY - rect.top;
      hoveredNode = pickNode(pointer.x, pointer.y);
      canvas.style.cursor = hoveredNode ? "pointer" : "default";
      updateSidebar();
    });

    canvas.addEventListener("mouseleave", () => {
      hoveredNode = null;
      updateSidebar();
    });

    canvas.addEventListener("click", () => {
      const node = hoveredNode || pickNode(pointer.x, pointer.y);
      if (!node) {
        currentView.selectedId = null;
        updateSidebar();
        return;
      }

      currentView.selectedId = node.id;
      updateSidebar();

      if (currentView === overview && details[node.id]) {
        switchView(details[node.id]);
      }
    });

    backButton.addEventListener("click", () => switchView(overview));
    recenterButton.addEventListener("click", () => seedLayout(currentView));
    window.addEventListener("resize", resizeCanvas);

    function frame() {
      tick = performance.now();
      stepSimulation();
      drawGraph();
      requestAnimationFrame(frame);
    }

    renderEmptyState();
    updateSidebar();
    resizeCanvas();
    frame();
  </script>
</body>
</html>
"""
    return (
        template.replace("__PROJECT__", data["project"])
        .replace("__GENERATED_AT__", data["generatedAt"])
        .replace("__PAYLOAD__", payload)
        .replace("__COLOR_MAP__", color_map)
    )


def main() -> None:
    data = load_data()
    html = build_html(data)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote star map to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
