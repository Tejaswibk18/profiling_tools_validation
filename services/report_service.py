import datetime
from pathlib import Path
from services.logger_service import log_error

def generate_html_report(module_key):
    """
    Generates an HTML report based on the validation results for the module.
    """
    try:
        report_dir = Path("reports/html")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"{module_key}_report.html"

        base_outputs_path = Path(f"outputs/{module_key}")
        
        env_stats = {}
        global_passed = 0
        global_failed = 0
        failure_reasons = []
        validation_details = []

        if base_outputs_path.exists():
            for results_path in base_outputs_path.glob("**/validation_results.txt"):
                try:
                    rel_parts = results_path.relative_to(base_outputs_path).parts
                    if len(rel_parts) >= 3:
                        os_type = rel_parts[0].upper()
                        mode = rel_parts[1]
                        server_name = rel_parts[2]
                        env_name = f"{os_type} ({server_name})"
                    elif len(rel_parts) == 2:
                        os_type = rel_parts[0].upper()
                        mode = rel_parts[1]
                        env_name = os_type
                    else:
                        env_name = "UNKNOWN"
                        mode = "unknown"
                        
                    if env_name not in env_stats:
                        env_stats[env_name] = {"passed": 0, "failed": 0}
                        
                    with open(results_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue
                            
                            validation_details.append({"env": env_name, "mode": mode, "text": line})
                            
                            if line.startswith("[PASS]"):
                                env_stats[env_name]["passed"] += 1
                                global_passed += 1
                            elif line.startswith("[FAIL]") or line.startswith("[ERROR]"):
                                env_stats[env_name]["failed"] += 1
                                global_failed += 1
                                failure_reasons.append(f"[{env_name}][{mode}] {line}")
                except Exception as ex:
                    print(f"[WARN] Failed to process validation results at {results_path}: {ex}")
        else:
            failure_reasons.append(f"Base outputs directory not found at {base_outputs_path}")

        total_validations = global_passed + global_failed
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Execution Report - {module_key.upper()}</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0f172a;
            --glass-bg: rgba(30, 41, 59, 0.7);
            --glass-border: rgba(255, 255, 255, 0.1);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-pass: #10b981;
            --accent-fail: #ef4444;
            --accent-info: #3b82f6;
            --gradient-pass: linear-gradient(135deg, #059669 0%, #10b981 100%);
            --gradient-fail: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
            --gradient-primary: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
        }}
        
        body {{
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.15) 0px, transparent 50%),
                radial-gradient(at 100% 0%, rgba(168, 85, 247, 0.15) 0px, transparent 50%);
            color: var(--text-primary);
            margin: 0;
            padding: 40px;
            box-sizing: border-box;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        header {{
            text-align: center;
            margin-bottom: 50px;
            animation: fadeInDown 0.8s ease-out;
        }}
        
        h1 {{
            font-size: 3rem;
            font-weight: 800;
            margin-bottom: 10px;
            background: var(--gradient-primary);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.05em;
        }}
        
        .timestamp {{
            color: var(--text-secondary);
            font-size: 1.1rem;
            font-weight: 300;
        }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }}
        
        .card {{
            background: var(--glass-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            padding: 30px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            animation: fadeIn 0.8s ease-out;
        }}
        
        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.4);
            border-color: rgba(255, 255, 255, 0.2);
        }}
        
        .stat-value {{
            font-size: 3.5rem;
            font-weight: 800;
            margin: 10px 0;
            line-height: 1;
        }}
        
        .stat-label {{
            color: var(--text-secondary);
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 600;
        }}
        
        .card-pass {{ border-left: 5px solid var(--accent-pass); }}
        .card-fail {{ border-left: 5px solid var(--accent-fail); }}
        
        .card-pass .stat-value {{ color: var(--accent-pass); }}
        .card-fail .stat-value {{ color: var(--accent-fail); }}
        
        .env-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        
        .env-card {{
            background: rgba(30, 41, 59, 0.4);
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            padding: 20px;
            text-align: center;
            transition: all 0.3s ease;
        }}
        
        .env-card:hover {{
            background: rgba(30, 41, 59, 0.6);
            border-color: var(--accent-info);
        }}
        
        .env-card h3 {{
            margin-top: 0;
            font-size: 1.3rem;
            color: var(--text-primary);
            border-bottom: 1px solid var(--glass-border);
            padding-bottom: 10px;
        }}
        
        .env-stat {{
            display: flex;
            justify-content: space-around;
            margin-top: 15px;
        }}
        
        .env-stat-item {{
            text-align: center;
        }}
        
        .env-stat-item span {{
            display: block;
            font-size: 1.5rem;
            font-weight: 700;
        }}
        
        .env-stat-item label {{
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}
        
        .env-pass {{ color: var(--accent-pass); }}
        .env-fail {{ color: var(--accent-fail); }}
        
        .section-title {{
            font-size: 1.8rem;
            font-weight: 700;
            margin: 40px 0 20px 0;
            position: relative;
            padding-left: 15px;
        }}
        
        .section-title::before {{
            content: '';
            position: absolute;
            left: 0;
            top: 50%;
            transform: translateY(-50%);
            width: 5px;
            height: 25px;
            background: var(--gradient-primary);
            border-radius: 3px;
        }}
        
        .log-container {{
            background: #0b1329;
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            padding: 25px;
            height: 400px;
            overflow-y: auto;
            font-family: 'Fira Code', monospace;
            font-size: 0.9rem;
        }}
        
        .log-line {{
            margin-bottom: 8px;
            padding: 6px 12px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.02);
            border-left: 3px solid transparent;
            transition: background 0.2s ease;
        }}
        
        .log-line:hover {{
            background: rgba(255, 255, 255, 0.05);
        }}
        
        .log-pass {{ border-left-color: var(--accent-pass); color: #a7f3d0; }}
        .log-fail {{ border-left-color: var(--accent-fail); color: #fecaca; }}
        .log-error {{ border-left-color: #f59e0b; color: #fef08a; }}
        
        .failures-box {{
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            border-radius: 16px;
            padding: 25px;
            margin-bottom: 40px;
        }}
        
        .failures-box h2 {{
            color: #fca5a5;
            margin-top: 0;
        }}
        
        .failures-box li {{
            margin-bottom: 10px;
            color: #fecaca;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        @keyframes fadeInDown {{
            from {{ opacity: 0; transform: translateY(-20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        ::-webkit-scrollbar {{ width: 8px; }}
        ::-webkit-scrollbar-track {{ background: rgba(0,0,0,0.1); }}
        ::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.1); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: rgba(255,255,255,0.2); }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Execution Report for Module: {module_key.upper()}</h1>
            <div class="timestamp">Generated on {timestamp}</div>
        </header>
        
        <div class="grid">
            <div class="card">
                <div class="stat-label">Total Validations</div>
                <div class="stat-value" style="color: var(--text-primary);">{total_validations}</div>
                <div style="color: var(--text-secondary);">Across {len(env_stats)} environments</div>
            </div>
            <div class="card card-pass">
                <div class="stat-label">Passed</div>
                <div class="stat-value">{global_passed}</div>
                <div style="color: var(--text-secondary);">Successful checks</div>
            </div>
            <div class="card card-fail">
                <div class="stat-label">Failed</div>
                <div class="stat-value">{global_failed}</div>
                <div style="color: var(--text-secondary);">Issues detected</div>
            </div>
        </div>
        
        <div class="section-title">Environment Breakdown</div>
        <div class="env-grid">
"""

        for env, stats in env_stats.items():
            html_content += f"""
            <div class="env-card">
                <h3>{env}</h3>
                <div class="env-stat">
                    <div class="env-stat-item">
                        <span class="env-pass">{stats['passed']}</span>
                        <label>Passed</label>
                    </div>
                    <div class="env-stat-item">
                        <span class="env-fail">{stats['failed']}</span>
                        <label>Failed</label>
                    </div>
                </div>
            </div>
            """

        html_content += """
        </div>
        """

        if global_failed > 0 or failure_reasons:
            html_content += """
            <div class="failures-box">
                <h2>Critical Failures & Errors</h2>
                <ul>
            """
            for reason in failure_reasons:
                html_content += f"<li>{reason}</li>"
            html_content += """
                </ul>
            </div>
            """
            
        html_content += """
        <div class="section-title">Detailed Validation Logs</div>
        <div class="log-container">
        """
        
        for detail in validation_details:
            text = detail['text']
            log_class = "log-pass" if "[PASS]" in text else "log-fail" if "[FAIL]" in text else "log-error" if "[ERROR]" in text else ""
            html_content += f"<div class='log-line {log_class}'>[{detail['env']}][{detail['mode']}] {text}</div>"
        
        html_content += """
        </div>
    </div>
</body>
</html>
"""

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"[INFO] Successfully generated HTML report: {report_file}")

    except Exception as error:
        message = f"Failed to generate HTML report : {error}"
        print(f"\n[ERROR] {message}")
        log_error(message)
