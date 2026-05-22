import datetime
from pathlib import Path
from services.logger_service import log_error


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_html_report(module_key):
    """
    Generates an HTML report for the given module key (pp / wp).

    Changes vs. previous version:
    - All environments are shown, even ones that only have a connection_error.txt
      (e.g. Windows that failed authentication).
    - Stats are based on test-case counts, not file counts.
    - Each environment card shows a per-mode (sudo / non-sudo) breakdown.
    - Detailed logs include the full message for every [PASS] and [FAIL] line.
    - Filter buttons (All / Passed / Failed) let the user narrow the log view.
    """
    try:
        module_name = "Platform Profiler" if module_key.lower() == "pp" else "Workload Profiler" if module_key.lower() == "wp" else module_key.upper()
        report_dir = Path("reports/html")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"{module_key}_report.html"

        base_outputs_path = Path(f"outputs/{module_key}")

        # env_stats shape:
        # {
        #   "LINUX": {
        #       "sudo":    {"passed": 0, "failed": 0, "total": 0, "label": "Sudo"},
        #       "nonsudo": {"passed": 0, "failed": 0, "total": 0, "label": "Non-Sudo"},
        #       "error": None   <-- or error string if connection failed
        #   },
        #   "WINDOWS": { ..., "error": "Authentication Failed for windows" }
        # }
        env_stats = {}
        global_passed = 0
        global_failed = 0
        failure_reasons = []
        validation_details = []   # list of {env, mode, text}

        if base_outputs_path.exists():

            # Pass 1 – collect connection errors written by ssh_service
            for err_path in sorted(base_outputs_path.glob("*/connection_error.txt")):
                os_name = err_path.parent.name.upper()
                try:
                    with open(err_path, "r", encoding="utf-8") as fh:
                        err_msg = fh.read().strip()
                    if os_name not in env_stats:
                        env_stats[os_name] = _fresh_env(err_msg)
                except Exception:
                    pass

            # Pass 2 – process validation_results.txt files
            for res_path in sorted(base_outputs_path.glob("**/validation_results.txt")):
                try:
                    dir_parts = res_path.relative_to(base_outputs_path).parts[:-1]
                    if len(dir_parts) < 2:
                        continue

                    os_name   = dir_parts[0].upper()
                    mode_dir  = dir_parts[1]
                    mode_key, mode_label = _resolve_mode(mode_dir)

                    if os_name not in env_stats:
                        env_stats[os_name] = _fresh_env(None)

                    # Keep the display label correct (e.g. "Administrator" for Windows)
                    env_stats[os_name][mode_key]["label"] = mode_label

                    with open(res_path, "r", encoding="utf-8") as fh:
                        for raw in fh:
                            line = raw.strip()
                            if not line:
                                continue

                            validation_details.append(
                                {"env": os_name, "mode": mode_label, "text": line}
                            )
                            env_stats[os_name][mode_key]["total"] += 1

                            if line.startswith("[PASS]"):
                                env_stats[os_name][mode_key]["passed"] += 1
                                global_passed += 1
                            elif line.startswith("[FAIL]") or line.startswith("[ERROR]"):
                                env_stats[os_name][mode_key]["failed"] += 1
                                global_failed += 1
                                failure_reasons.append(
                                    f"[{os_name}][{mode_label}] {line}"
                                )

                except Exception as ex:
                    print(f"[WARN] Failed to process validation results at {res_path}: {ex}")

        else:
            failure_reasons.append(
                f"Base outputs directory not found at {base_outputs_path}"
            )

        total_tests  = global_passed + global_failed
        timestamp    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        env_list_str = " · ".join(env_stats.keys()) if env_stats else "None"

        html = _build_html(
            module_key, timestamp,
            total_tests, global_passed, global_failed,
            env_stats, env_list_str,
            failure_reasons, validation_details,
        )

        with open(report_file, "w", encoding="utf-8") as fh:
            fh.write(html)

        print(f"[INFO] Successfully generated HTML report for {module_name}: {report_file}")

    except Exception as error:
        message = f"Failed to generate HTML report : {error}"
        print(f"\n[ERROR] {message}")
        log_error(message)


# ---------------------------------------------------------------------------
# Helpers – data
# ---------------------------------------------------------------------------

def _fresh_env(error_msg):
    return {
        "sudo":    {"passed": 0, "failed": 0, "total": 0, "label": "Sudo"},
        "nonsudo": {"passed": 0, "failed": 0, "total": 0, "label": "Non-Sudo"},
        "error":   error_msg,
    }


def _resolve_mode(mode_dir):
    """Map folder name → (internal_key, display_label)."""
    if mode_dir in ("sudo", "administrator"):
        return "sudo", ("Administrator" if mode_dir == "administrator" else "Sudo")
    return "nonsudo", ("Normal User" if mode_dir == "normal user" else "Non-Sudo")


# ---------------------------------------------------------------------------
# Helpers – HTML fragments
# ---------------------------------------------------------------------------

_ENV_ICONS = {
    "LINUX": "🐧", "ARM": "💪", "WINDOWS": "🪟",
    "GPU": "🎮",   "CLOUD": "☁️", "GPU_CLUSTER": "⚡",
}


def _env_cards(env_stats):
    parts = []
    for os_name, data in env_stats.items():
        icon = _ENV_ICONS.get(os_name, "🖥️")

        if data["error"]:
            parts.append(f"""
            <div class="env-card env-card-error">
                <div class="env-header">
                    <span class="env-icon">{icon}</span>
                    <span class="env-name">{os_name}</span>
                    <span class="env-badge badge-error">● CONNECTION ERROR</span>
                </div>
                <div class="error-message">⚠&nbsp; {data['error']}</div>
            </div>""")
            continue

        sudo    = data["sudo"]
        nonsudo = data["nonsudo"]
        total_env  = sudo["total"]    + nonsudo["total"]
        failed_env = sudo["failed"]   + nonsudo["failed"]

        badge_cls = "badge-ok"   if failed_env == 0 else "badge-warn"
        badge_txt = "● ALL PASSED" if failed_env == 0 else f"● {failed_env} FAILED"

        s_pct = int(sudo["passed"]    / sudo["total"]    * 100) if sudo["total"]    else 0
        n_pct = int(nonsudo["passed"] / nonsudo["total"] * 100) if nonsudo["total"] else 0

        parts.append(f"""
            <div class="env-card">
                <div class="env-header">
                    <span class="env-icon">{icon}</span>
                    <span class="env-name">{os_name}</span>
                    <span class="env-badge {badge_cls}">{badge_txt}</span>
                </div>
                <div class="total-row">
                    <span class="total-label">Total Test Cases</span>
                    <span class="total-value">{total_env}</span>
                </div>
                <div class="mode-sections">
                    <div class="mode-block">
                        <div class="mode-title">{sudo['label']}</div>
                        <div class="mode-stats">
                            <div class="mode-stat"><span class="mode-val">{sudo['total']}</span><label>Total</label></div>
                            <div class="mode-stat"><span class="mode-val text-pass">{sudo['passed']}</span><label>Passed</label></div>
                            <div class="mode-stat"><span class="mode-val text-fail">{sudo['failed']}</span><label>Failed</label></div>
                        </div>
                        <div class="progress-bar"><div class="progress-fill" style="width:{s_pct}%"></div></div>
                    </div>
                    <div class="mode-block">
                        <div class="mode-title">{nonsudo['label']}</div>
                        <div class="mode-stats">
                            <div class="mode-stat"><span class="mode-val">{nonsudo['total']}</span><label>Total</label></div>
                            <div class="mode-stat"><span class="mode-val text-pass">{nonsudo['passed']}</span><label>Passed</label></div>
                            <div class="mode-stat"><span class="mode-val text-fail">{nonsudo['failed']}</span><label>Failed</label></div>
                        </div>
                        <div class="progress-bar"><div class="progress-fill" style="width:{n_pct}%"></div></div>
                    </div>
                </div>
            </div>""")

    return "\n".join(parts)


def _log_lines(validation_details):
    lines = []
    for d in validation_details:
        text = d["text"]
        if "[PASS]" in text:
            cls, dtype = "log-pass", "pass"
        elif "[FAIL]" in text or "[ERROR]" in text:
            cls, dtype = "log-fail", "fail"
        else:
            cls, dtype = "", "other"

        lines.append(
            f'<div class="log-line {cls}" data-type="{dtype}">'
            f'<span class="log-env">[{d["env"]}]</span>'
            f'<span class="log-mode">[{d["mode"]}]</span>'
            f'<span class="log-text">{text}</span>'
            f'</div>'
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def _build_html(module_key, timestamp,
                total_tests, global_passed, global_failed,
                env_stats, env_list_str,
                failure_reasons, validation_details):

    module_name = "Platform Profiler" if module_key.lower() == "pp" else "Workload Profiler" if module_key.lower() == "wp" else module_key.upper()

    failures_html = ""
    if failure_reasons:
        li_items = "".join(f"<li>{r}</li>" for r in failure_reasons)
        failures_html = f"""
        <div class="failures-box">
            <h2>⚠ Critical Failures &amp; Errors</h2>
            <ul>{li_items}</ul>
        </div>"""

    cards = _env_cards(env_stats)
    logs  = _log_lines(validation_details)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Execution Report - {module_name}</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg:     #0f172a;
            --glass:  rgba(30,41,59,0.7);
            --border: rgba(255,255,255,0.1);
            --text:   #f8fafc;
            --muted:  #94a3b8;
            --pass:   #10b981;
            --fail:   #ef4444;
            --info:   #3b82f6;
            --warn:   #f59e0b;
            --grad:   linear-gradient(135deg,#6366f1,#a855f7);
        }}
        * {{ box-sizing:border-box; margin:0; padding:0; }}
        body {{
            font-family:'Outfit',sans-serif;
            background:var(--bg);
            background-image:
                radial-gradient(at 0% 0%,   rgba(99,102,241,0.15) 0, transparent 50%),
                radial-gradient(at 100% 0%, rgba(168,85,247,0.15)  0, transparent 50%);
            color:var(--text);
            padding:40px;
            min-height:100vh;
        }}
        .container {{ max-width:1320px; margin:0 auto; }}

        /* ── Header ── */
        header {{ text-align:center; margin-bottom:50px; animation:fadeInDown 0.8s ease; }}
        h1 {{
            font-size:2.8rem; font-weight:800;
            background:var(--grad);
            -webkit-background-clip:text; -webkit-text-fill-color:transparent;
            letter-spacing:-0.03em; margin-bottom:8px;
        }}
        .timestamp {{ color:var(--muted); font-size:1rem; font-weight:300; }}

        /* ── Summary Cards ── */
        .stats-grid {{
            display:grid;
            grid-template-columns:repeat(4,1fr);
            gap:20px; margin-bottom:50px;
            animation:fadeIn 0.8s ease;
        }}
        @media(max-width:900px){{ .stats-grid{{grid-template-columns:repeat(2,1fr);}} }}
        .stat-card {{
            background:var(--glass); backdrop-filter:blur(12px);
            border:1px solid var(--border); border-radius:20px; padding:28px;
            transition:all 0.3s ease;
        }}
        .stat-card:hover {{ transform:translateY(-4px); box-shadow:0 20px 40px rgba(0,0,0,0.4); border-color:rgba(255,255,255,0.2); }}
        .stat-label {{ font-size:0.78rem; text-transform:uppercase; letter-spacing:0.1em; color:var(--muted); font-weight:600; margin-bottom:8px; }}
        .stat-value {{ font-size:3rem; font-weight:800; line-height:1; margin-bottom:8px; }}
        .stat-sub   {{ font-size:0.83rem; color:var(--muted); }}
        .card-tests {{ border-left:4px solid var(--info);  }} .card-tests .stat-value {{ color:var(--info);  }}
        .card-pass  {{ border-left:4px solid var(--pass);  }} .card-pass  .stat-value {{ color:var(--pass);  }}
        .card-fail  {{ border-left:4px solid var(--fail);  }} .card-fail  .stat-value {{ color:var(--fail);  }}
        .card-env   .stat-value {{ color:#c084fc; }}

        /* ── Section Title ── */
        .section-title {{
            font-size:1.6rem; font-weight:700;
            margin:40px 0 20px; padding-left:15px; position:relative;
        }}
        .section-title::before {{
            content:''; position:absolute; left:0; top:50%; transform:translateY(-50%);
            width:4px; height:22px; background:var(--grad); border-radius:3px;
        }}

        /* ── Environment Cards ── */
        .env-grid {{
            display:grid;
            grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
            gap:22px; margin-bottom:40px;
        }}
        .env-card {{
            background:rgba(30,41,59,0.5); border:1px solid var(--border);
            border-radius:18px; padding:24px; transition:all 0.3s ease;
        }}
        .env-card:hover {{ background:rgba(30,41,59,0.75); transform:translateY(-3px); box-shadow:0 14px 32px rgba(0,0,0,0.35); }}
        .env-card-error {{ border-color:rgba(239,68,68,0.35); background:rgba(239,68,68,0.05); }}

        .env-header {{
            display:flex; align-items:center; gap:10px;
            margin-bottom:18px; padding-bottom:14px; border-bottom:1px solid var(--border);
        }}
        .env-icon  {{ font-size:1.5rem; }}
        .env-name  {{ font-size:1.2rem; font-weight:700; letter-spacing:0.05em; flex:1; }}
        .env-badge {{
            font-size:0.7rem; font-weight:700; padding:4px 11px;
            border-radius:20px; letter-spacing:0.04em;
        }}
        .badge-ok    {{ background:rgba(16,185,129,0.15); color:var(--pass); border:1px solid rgba(16,185,129,0.3); }}
        .badge-warn  {{ background:rgba(245,158,11,0.15);  color:var(--warn); border:1px solid rgba(245,158,11,0.3);  }}
        .badge-error {{ background:rgba(239,68,68,0.15);   color:var(--fail); border:1px solid rgba(239,68,68,0.3);   }}

        .error-message {{
            color:#fca5a5; font-size:0.88rem;
            padding:12px; background:rgba(239,68,68,0.1);
            border-radius:10px; border:1px solid rgba(239,68,68,0.2);
        }}

        /* Total test cases row inside env card */
        .total-row {{
            display:flex; justify-content:space-between; align-items:center;
            margin-bottom:14px; padding:10px 14px;
            background:rgba(99,102,241,0.1); border-radius:10px;
            border:1px solid rgba(99,102,241,0.2);
        }}
        .total-label {{ font-size:0.75rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.05em; }}
        .total-value {{ font-size:1.4rem; font-weight:800; color:#818cf8; }}

        /* Mode blocks */
        .mode-sections {{ display:flex; flex-direction:column; gap:10px; }}
        .mode-block {{
            background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06);
            border-radius:12px; padding:14px;
        }}
        .mode-title {{ font-size:0.73rem; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; color:var(--muted); margin-bottom:10px; }}
        .mode-stats {{ display:flex; justify-content:space-around; margin-bottom:10px; }}
        .mode-stat  {{ text-align:center; }}
        .mode-val   {{ display:block; font-size:1.6rem; font-weight:800; line-height:1; margin-bottom:2px; }}
        .mode-stat label {{ font-size:0.68rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.05em; }}
        .text-pass {{ color:var(--pass); }}
        .text-fail {{ color:var(--fail); }}
        .progress-bar  {{ height:4px; background:rgba(255,255,255,0.08); border-radius:4px; overflow:hidden; }}
        .progress-fill {{ height:100%; background:linear-gradient(135deg,#059669,#10b981); border-radius:4px; }}

        /* ── Failures box ── */
        .failures-box {{ background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.25); border-radius:16px; padding:24px; margin-bottom:40px; }}
        .failures-box h2 {{ color:#fca5a5; font-size:1.2rem; margin-bottom:16px; }}
        .failures-box ul {{ list-style:none; display:flex; flex-direction:column; gap:8px; }}
        .failures-box li {{ color:#fecaca; font-size:0.87rem; padding:8px 12px; background:rgba(239,68,68,0.08); border-radius:8px; border-left:3px solid var(--fail); word-break:break-word; }}

        /* ── Log filters ── */
        .log-filters {{ display:flex; gap:10px; margin-bottom:14px; flex-wrap:wrap; }}
        .filter-btn {{
            padding:8px 20px; border-radius:20px;
            border:1px solid var(--border); background:rgba(255,255,255,0.05);
            color:var(--muted); cursor:pointer;
            font-family:'Outfit',sans-serif; font-size:0.83rem; font-weight:600;
            transition:all 0.2s ease;
        }}
        .filter-btn:hover {{ background:rgba(255,255,255,0.1); color:var(--text); }}
        .filter-btn.active {{ background:var(--grad); border-color:transparent; color:#fff; }}

        /* ── Log container ── */
        .log-container {{
            background:#080f1e; border:1px solid var(--border);
            border-radius:16px; padding:20px;
            max-height:540px; overflow-y:auto;
            font-size:0.86rem;
        }}
        .log-line {{
            display:flex; align-items:flex-start; gap:8px;
            padding:8px 10px; border-radius:6px;
            margin-bottom:4px; border-left:3px solid transparent;
            transition:background 0.15s ease; line-height:1.55;
        }}
        .log-line:hover {{ background:rgba(255,255,255,0.04); }}
        .log-pass {{ border-left-color:var(--pass); }}
        .log-fail {{ border-left-color:var(--fail); }}
        .log-env  {{ font-weight:700; color:#818cf8; white-space:nowrap; font-size:0.76rem; padding-top:2px; flex-shrink:0; }}
        .log-mode {{ font-weight:600; color:var(--muted); white-space:nowrap; font-size:0.76rem; padding-top:2px; flex-shrink:0; }}
        .log-text {{ color:var(--muted); word-break:break-word; }}
        .log-pass .log-text {{ color:#a7f3d0; }}
        .log-fail .log-text {{ color:#fecaca; }}

        /* ── Animations ── */
        @keyframes fadeIn     {{ from{{opacity:0;transform:translateY(10px)}}  to{{opacity:1;transform:translateY(0)}} }}
        @keyframes fadeInDown {{ from{{opacity:0;transform:translateY(-20px)}} to{{opacity:1;transform:translateY(0)}} }}
        ::-webkit-scrollbar       {{ width:6px; }}
        ::-webkit-scrollbar-track {{ background:rgba(0,0,0,0.1); }}
        ::-webkit-scrollbar-thumb {{ background:rgba(255,255,255,0.1); border-radius:4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background:rgba(255,255,255,0.2); }}
    </style>
</head>
<body>
    <div class="container">

        <header>
            <h1>Execution Report — {module_name}</h1>
            <div class="timestamp">Generated on {timestamp}</div>
        </header>

        <!-- Summary cards -->
        <div class="stats-grid">
            <div class="stat-card card-tests">
                <div class="stat-label">Total Test Cases</div>
                <div class="stat-value">{total_tests}</div>
                <div class="stat-sub">Across {len(env_stats)} environment(s)</div>
            </div>
            <div class="stat-card card-pass">
                <div class="stat-label">Passed</div>
                <div class="stat-value">{global_passed}</div>
                <div class="stat-sub">Successful validations</div>
            </div>
            <div class="stat-card card-fail">
                <div class="stat-label">Failed</div>
                <div class="stat-value">{global_failed}</div>
                <div class="stat-sub">Issues detected</div>
            </div>
            <div class="stat-card card-env">
                <div class="stat-label">Environments</div>
                <div class="stat-value">{len(env_stats)}</div>
                <div class="stat-sub">{env_list_str}</div>
            </div>
        </div>

        <!-- Environment breakdown -->
        <div class="section-title">Environment Breakdown</div>
        <div class="env-grid">
            {cards}
        </div>

        {failures_html}

        <!-- Detailed validation logs -->
        <div class="section-title">Detailed Validation Logs</div>
        <div class="log-filters">
            <button class="filter-btn active" id="btn-all"  onclick="filterLogs('all')">All&nbsp;({total_tests})</button>
            <button class="filter-btn"         id="btn-pass" onclick="filterLogs('pass')">✓&nbsp;Passed&nbsp;({global_passed})</button>
            <button class="filter-btn"         id="btn-fail" onclick="filterLogs('fail')">✗&nbsp;Failed&nbsp;({global_failed})</button>
        </div>
        <div class="log-container" id="log-container">
            {logs}
        </div>

    </div>

    <script>
        function filterLogs(type) {{
            ['all','pass','fail'].forEach(function(t) {{
                document.getElementById('btn-' + t).classList.remove('active');
            }});
            document.getElementById('btn-' + type).classList.add('active');
            document.querySelectorAll('.log-line').forEach(function(el) {{
                var dt = el.getAttribute('data-type');
                el.style.display = (type === 'all' || dt === type) ? 'flex' : 'none';
            }});
        }}
    </script>
</body>
</html>"""
