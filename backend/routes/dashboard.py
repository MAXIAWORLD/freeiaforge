from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from routes.chat import get_router
from services.stats_history import get_last_7_days

router = APIRouter()

_CIRCUIT_BADGE = {
    "CLOSED": '<span style="color:#22c55e;font-weight:bold">CLOSED</span>',
    "HALF_OPEN": '<span style="color:#f59e0b;font-weight:bold">HALF_OPEN</span>',
    "OPEN": '<span style="color:#ef4444;font-weight:bold">OPEN</span>',
}


def _build_html(version: str, statuses: list, daily_stats: dict, history: list | None = None) -> str:
    rows = ""
    for p in statuses:
        badge = _CIRCUIT_BADGE.get(p.circuit_status, p.circuit_status)
        quota_pct = round(p.requests_used / p.requests_limit * 100, 1) if p.requests_limit else 0
        last_err = p.last_error or "—"
        rows += (
            f"<tr>"
            f"<td>{p.name}</td>"
            f"<td>{badge}</td>"
            f"<td>{p.requests_used}/{p.requests_limit} ({quota_pct}%)</td>"
            f"<td>{p.tokens_used:,}/{p.tokens_limit:,}</td>"
            f"<td>{p.consecutive_errors}</td>"
            f"<td style='max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap' title='{last_err}'>{last_err}</td>"
            f"</tr>"
        )

    total = daily_stats.get("total", 0)
    by_task = daily_stats.get("by_task", {})
    task_rows = "".join(
        f"<tr><td>{t}</td><td>{c}</td></tr>" for t, c in sorted(by_task.items())
    ) or "<tr><td colspan='2' style='color:#888'>no requests yet</td></tr>"

    hist = history or []
    history_rows = "".join(
        f"<tr><td>{row['day']}</td><td>{row['task_type']}</td><td>{row['provider']}</td>"
        f"<td>{row['requests']}</td><td>{row['tokens']:,}</td></tr>"
        for row in hist
    ) or "<tr><td colspan='5' style='color:#888'>no data yet</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="30">
<title>FreeIA Gateway</title>
<style>
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:24px}}
  h1{{color:#38bdf8;margin:0 0 4px}}
  .sub{{color:#64748b;margin:0 0 24px;font-size:.9rem}}
  table{{border-collapse:collapse;width:100%;margin-bottom:32px}}
  th{{background:#1e293b;color:#94a3b8;text-align:left;padding:10px 14px;font-size:.8rem;text-transform:uppercase;letter-spacing:.05em}}
  td{{padding:10px 14px;border-bottom:1px solid #1e293b;font-size:.9rem}}
  tr:hover td{{background:#1e293b}}
  .stats{{display:flex;gap:16px;margin-bottom:32px}}
  .card{{background:#1e293b;border-radius:8px;padding:16px 24px;min-width:140px}}
  .card-val{{font-size:2rem;font-weight:700;color:#38bdf8}}
  .card-lbl{{font-size:.75rem;color:#64748b;text-transform:uppercase}}
  footer{{color:#475569;font-size:.8rem;margin-top:8px}}
</style>
</head>
<body>
<h1>FreeIA Gateway</h1>
<p class="sub">v{version} &mdash; auto-refresh every 30s</p>

<div class="stats">
  <div class="card">
    <div class="card-val">{total}</div>
    <div class="card-lbl">requests today</div>
  </div>
  <div class="card">
    <div class="card-val">{len(statuses)}</div>
    <div class="card-lbl">providers</div>
  </div>
</div>

<h2 style="color:#94a3b8;font-size:1rem;text-transform:uppercase;letter-spacing:.05em">Providers</h2>
<table>
  <thead>
    <tr>
      <th>Provider</th><th>Circuit</th><th>Requests</th><th>Tokens</th><th>Errors</th><th>Last error</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>

<h2 style="color:#94a3b8;font-size:1rem;text-transform:uppercase;letter-spacing:.05em">Today by task type</h2>
<table style="max-width:360px">
  <thead><tr><th>Task</th><th>Count</th></tr></thead>
  <tbody>{task_rows}</tbody>
</table>

<h2 style="color:#94a3b8;font-size:1rem;text-transform:uppercase;letter-spacing:.05em">Last 7 days</h2>
<table>
  <thead><tr><th>Day</th><th>Task</th><th>Provider</th><th>Requests</th><th>Tokens</th></tr></thead>
  <tbody>{history_rows}</tbody>
</table>

<footer>FreeIA Gateway &mdash; powered by <a href="https://maxiaworld.app" style="color:#38bdf8">MAXIA</a></footer>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request) -> HTMLResponse:
    r = get_router()
    statuses = await r.get_provider_statuses()
    daily_stats = r.get_daily_stats()
    stats_db = getattr(r, "_stats_db", None)
    history = await get_last_7_days(stats_db) if stats_db is not None else []
    html = _build_html(request.app.version, statuses, daily_stats, history)
    return HTMLResponse(content=html)
