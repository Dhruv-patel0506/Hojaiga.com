# brain/universal_renderer.py
import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import numpy as np


class HojaigaUniversalRenderer:
    """
    Zero-Hardcoding Universal Multimodal Renderer:
    Transforms ANY input (text, JSON workflow, concept triples, image/diagram array, or video array)
    into an interactive HTML5 canvas with:
    - 2D Animated Pathway & Flow Particles
    - 3D Rotatable & Zoomable Spatial Graph
    - 4-View Pepper's Ghost Hologram Pyramid
    Visual parameters (particle speed, node sizing, color temperature) are computed mathematically
    from the input's own entropy, edge density, and graph topology—with zero hardcoded keyword effects.
    """

    def extract_dynamic_graph(
        self,
        raw_input: Union[str, Dict[str, Any], np.ndarray],
        triples: List[Tuple[str, str, str]] = (),
    ) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        title = "Dynamic Brain Projection"
        entropy_metric = 0.5

        if isinstance(raw_input, np.ndarray):
            arr = raw_input[0] if raw_input.ndim == 4 else raw_input
            h, w, _ = arr.shape
            gray = np.mean(arr.astype(np.float32), axis=2)
            gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
            gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
            grad = (gx + gy) / 255.0
            entropy_metric = float(np.clip(np.std(gray) / 64.0, 0.1, 1.0))

            flat_indices = np.argsort(grad.ravel())[::-1][:8]
            for idx, flat_i in enumerate(flat_indices):
                ry, rx = divmod(int(flat_i), w)
                nodes.append(
                    {
                        "id": f"n{idx}",
                        "label": f"Region_{idx}@({rx/w:.2f},{ry/h:.2f})",
                        "x_norm": round((rx / max(w, 1)) * 2 - 1, 3),
                        "y_norm": round((ry / max(h, 1)) * 2 - 1, 3),
                        "weight": round(float(grad[ry, rx]), 3),
                    }
                )
            for i in range(len(nodes) - 1):
                edges.append({"source": i, "target": i + 1, "label": "spatial_flow"})
            title = f"Visual Topology ({w}x{h})"

        elif isinstance(raw_input, dict):
            title = str(next(iter(raw_input.values()), "Structured Graph"))[:40]
            keys = list(raw_input.keys())[:10]
            for idx, k in enumerate(keys):
                val_str = str(raw_input[k])[:28]
                nodes.append({"id": f"n{idx}", "label": f"{k}: {val_str}", "weight": 0.7})
            for i in range(len(nodes) - 1):
                edges.append({"source": i, "target": i + 1, "label": "link"})

        else:
            text = str(raw_input).strip()
            if text.startswith("{") and text.endswith("}"):
                try:
                    return self.extract_dynamic_graph(json.loads(text), triples=triples)
                except Exception:
                    pass
            chars = list(text)
            if chars:
                probs = [text.count(c) / len(chars) for c in set(chars)]
                entropy_metric = float(np.clip(-sum(p * np.log2(p) for p in probs) / 5.0, 0.15, 1.0))

            if triples:
                seen_labels: Dict[str, int] = {}
                for s, p, o in triples[:10]:
                    for lbl in (s, o):
                        if lbl not in seen_labels:
                            seen_labels[lbl] = len(nodes)
                            nodes.append({"id": f"n{len(nodes)}", "label": lbl[:32], "weight": 0.8})
                    edges.append({"source": seen_labels[s], "target": seen_labels[o], "label": p[:20]})
            else:
                segments = [s.strip() for s in re.split(r"->|→|=>|[.!?;:\n]+", text) if len(s.strip()) >= 2][:8]
                for idx, seg in enumerate(segments):
                    nodes.append({"id": f"n{idx}", "label": seg[:36], "weight": round(min(len(seg) / 30.0, 1.0), 3)})
                for i in range(len(nodes) - 1):
                    edges.append({"source": i, "target": i + 1, "label": "flow"})
            title = nodes[0]["label"] if nodes else "Dynamic Stream"

        return {
            "title": title,
            "entropy_energy": round(entropy_metric, 4),
            "nodes": nodes or [{"id": "n0", "label": "Root State", "weight": 1.0}],
            "edges": edges,
        }

    def render_to_html(
        self,
        raw_input: Union[str, Dict[str, Any], np.ndarray],
        output_file: Path,
        triples: List[Tuple[str, str, str]] = (),
    ) -> Path:
        scene = self.extract_dynamic_graph(raw_input, triples=triples)
        # "</" inside a <script> block would let input text close the script tag (HTML injection)
        scene_json = json.dumps(scene, ensure_ascii=False).replace("</", "<\\/")
        title_esc = html.escape(str(scene["title"]))

        html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title_esc}</title>
<style>
  body {{ margin: 0; background: #05070d; color: #e2e8f0; font-family: system-ui, sans-serif; overflow: hidden; }}
  #toolbar {{
    position: fixed; top: 14px; left: 14px; z-index: 10; display: flex; gap: 10px;
    background: rgba(15, 23, 42, 0.85); padding: 10px 14px; border-radius: 10px; border: 1px solid #334155;
  }}
  button {{
    background: #1e293b; color: #f8fafc; border: 1px solid #475569; padding: 8px 14px;
    border-radius: 6px; cursor: pointer; font-weight: 600;
  }}
  button.active {{ background: #2563eb; border-color: #60a5fa; }}
  #meta {{ position: fixed; bottom: 14px; left: 14px; z-index: 10; background: rgba(15,23,42,0.85);
    padding: 10px 14px; border-radius: 8px; border: 1px solid #334155; font-size: 13px; }}
  canvas {{ display: block; width: 100vw; height: 100vh; }}
</style>
</head>
<body>
<div id="toolbar">
  <button id="btn2d" class="active" onclick="setMode('2d')">2D Pathway</button>
  <button id="btn3d" onclick="setMode('3d')">3D Spatial Graph</button>
  <button id="btnholo" onclick="setMode('hologram')">Hologram (4-View Pyramid)</button>
</div>
<div id="meta"></div>
<canvas id="stage"></canvas>
<script>
const scene = {scene_json};
const canvas = document.getElementById('stage');
const ctx = canvas.getContext('2d');
let mode = '2d', rotX = 0.35, rotY = 0.55, zoom = 1.0, dragging = false, lx = 0, ly = 0, tick = 0;

function resize() {{ canvas.width = window.innerWidth; canvas.height = window.innerHeight; }}
window.addEventListener('resize', resize); resize();
document.getElementById('meta').innerText =
  `${{scene.title}} | Nodes: ${{scene.nodes.length}} | Edges: ${{scene.edges.length}} | Entropy Energy: ${{scene.entropy_energy}}`;

function setMode(m) {{
  mode = m;
  ['2d','3d','hologram'].forEach(k => document.getElementById('btn'+(k==='hologram'?'holo':k)).classList.toggle('active', k===m));
}}

canvas.addEventListener('mousedown', e => {{ dragging = true; lx = e.clientX; ly = e.clientY; }});
window.addEventListener('mouseup', () => dragging = false);
window.addEventListener('mousemove', e => {{
  if (!dragging) return;
  rotY += (e.clientX - lx) * 0.008; rotX += (e.clientY - ly) * 0.008;
  lx = e.clientX; ly = e.clientY;
}});
canvas.addEventListener('wheel', e => {{ zoom = Math.max(0.4, Math.min(2.8, zoom - e.deltaY * 0.001)); }});

function drawViewport(cx, cy, radius, angleOffset, scale) {{
  const nodes = scene.nodes;
  const hueBase = Math.round(190 + scene.entropy_energy * 110);
  const pts = nodes.map((n, idx) => {{
    const t = (idx / Math.max(nodes.length - 1, 1)) * Math.PI * 1.4 - Math.PI * 0.7;
    const x3 = (n.x_norm !== undefined ? n.x_norm : Math.cos(t)) * radius;
    const y3 = (n.y_norm !== undefined ? n.y_norm : Math.sin(t * 1.5) * 0.5) * radius;
    const z3 = Math.sin(t) * (mode === '2d' ? 0 : radius * 0.55);
    const ry = (mode === '2d' ? 0 : rotY) + angleOffset;
    const rx = mode === '2d' ? 0 : rotX;
    const x1 = x3 * Math.cos(ry) - z3 * Math.sin(ry);
    const z1 = x3 * Math.sin(ry) + z3 * Math.cos(ry);
    const y2 = y3 * Math.cos(rx) - z1 * Math.sin(rx);
    const z2 = y3 * Math.sin(rx) + z1 * Math.cos(rx);
    const persp = 450 / (450 + z2);
    return {{ x: cx + x1 * scale * persp, y: cy + y2 * scale * persp, label: n.label, weight: n.weight || 0.7, persp }};
  }});

  const speed = 0.008 + scene.entropy_energy * 0.02;
  scene.edges.forEach(e => {{
    const p1 = pts[e.source], p2 = pts[e.target];
    if (!p1 || !p2) return;
    ctx.strokeStyle = `hsl(${{hueBase}}, 80%, 60%)`;
    ctx.lineWidth = 2.5 * scale;
    ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();

    const frac = (tick * speed) % 1;
    const px = p1.x + (p2.x - p1.x) * frac;
    const py = p1.y + (p2.y - p1.y) * frac;
    ctx.fillStyle = '#facc15';
    ctx.beginPath(); ctx.arc(px, py, 4.5 * scale, 0, Math.PI * 2); ctx.fill();
  }});

  pts.forEach(p => {{
    const r = (10 + p.weight * 8) * scale * p.persp;
    ctx.fillStyle = `hsl(${{hueBase}}, 75%, 45%)`;
    ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.fillStyle = '#f8fafc'; ctx.font = `${{Math.max(10, Math.round(12 * scale * p.persp))}}px sans-serif`;
    ctx.fillText(p.label, p.x - 24 * scale, p.y - r - 6);
  }});
}}

function animate() {{
  tick++;
  ctx.fillStyle = '#05070d'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (mode === 'hologram') {{
    const cx = canvas.width / 2, cy = canvas.height / 2, off = Math.min(cx, cy) * 0.52;
    drawViewport(cx, cy - off, 110, 0, 0.55 * zoom);
    drawViewport(cx, cy + off, 110, Math.PI, 0.55 * zoom);
    drawViewport(cx - off, cy, 110, Math.PI / 2, 0.55 * zoom);
    drawViewport(cx + off, cy, 110, -Math.PI / 2, 0.55 * zoom);
  }} else {{
    if (mode === '3d' && !dragging) rotY += 0.004;
    drawViewport(canvas.width / 2, canvas.height / 2, 220, 0, zoom);
  }}
  requestAnimationFrame(animate);
}}
animate();
</script>
</body>
</html>"""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html_doc, encoding="utf-8")
        return output_file
