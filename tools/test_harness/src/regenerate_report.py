import os
import json
import datetime
import math

def get_stats(data_list):
    if not data_list:
        return None, None, None, None, None, None, None
    s_min = min(data_list)
    s_max = max(data_list)
    s_avg = sum(data_list) / len(data_list)
    sorted_data = sorted(data_list)
    
    def get_percentile(p):
        idx = int(len(sorted_data) * p)
        return sorted_data[min(idx, len(sorted_data) - 1)]
        
    s_p50 = get_percentile(0.50)
    s_p90 = get_percentile(0.90)
    s_p95 = get_percentile(0.95)
    s_p99 = get_percentile(0.99)
    return s_min, s_p50, s_p90, s_p95, s_p99, s_max, s_avg

def get_git_root():
    import subprocess
    try:
        res = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return os.getcwd()

def detect_connectors(scenario_name):
    connectors = []
    name_upper = scenario_name.upper()
    if "GDRIVE" in name_upper or "GOOGLE DRIVE" in name_upper or "HR EMPLOYEE HANDBOOK" in name_upper:
        connectors.append("Google Drive")
    if "CONFLUENCE" in name_upper:
        connectors.append("Confluence")
    if "JIRA" in name_upper:
        connectors.append("Jira")
    if "LUMAPPS" in name_upper or "GCS" in name_upper:
        connectors.append("LumApps (GCS)")
    if "3-WAY" in name_upper:
        connectors.extend(["LumApps (GCS)", "Confluence", "Jira"])
    if not connectors:
        connectors.append("Default Search Index")
    return list(set(connectors))

def get_scenario_base_name(name):
    base = name
    for suffix in [" (Stream)", " (UI)", " (Stream API)", " (UI Preview)"]:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
    if " - Gemini " in base:
        base = base.split(" - Gemini ")[0]
    return base

def regenerate(run_dir):
    results_path = os.path.join(run_dir, "results.json")
    print(f"Regenerating report from: {results_path}")
    
    with open(results_path, "r") as f:
        results_json = json.load(f)
        
    test_id = results_json["test_id"]
    model_used = results_json["model_used"]
    copied_manifest_git_rel = results_json["manifest_used"]
    max_concurrency = results_json["concurrency_limit"]
    total_duration_s = results_json["total_duration_seconds"]
    throughput_qpm = results_json["queries_per_minute"]
    
    # Load manifest file to extract configured scenarios
    manifest_name = os.path.basename(copied_manifest_git_rel)
    manifest_path = os.path.join(run_dir, manifest_name)
    with open(manifest_path, "r") as mf:
        manifest_data = json.load(mf)
    scenarios = manifest_data["scenarios"]
    query = manifest_data["query"]
    iterations = manifest_data["iterations"]
    
    project_id = manifest_data["project_id"]
    git_root = get_git_root()
    
    # Re-import chart link mappings
    from chart_generator import generate_charts_for_run
    chart_links = generate_charts_for_run(results_path, run_dir)
    
    if test_id == "verify":
        report_title = "GE Benchmarking Testing Report: Verification Run"
    else:
        report_title = f"GE Benchmarking Testing Report: Run {test_id}"
        
    # Read templates
    config_dir = os.path.join(git_root, "tools/test_harness/config")
    try:
        with open(os.path.join(config_dir, "report_template.md"), "r") as f:
            report_template = f.read()
        with open(os.path.join(config_dir, "scenario_template.md"), "r") as f:
            scenario_template = f.read()
        with open(os.path.join(config_dir, "screenshot_template.md"), "r") as f:
            screenshot_template = f.read()
    except Exception as e:
        print(f"Error loading report templates from {config_dir}: {e}")
        raise e

    readme_abs = os.path.abspath(os.path.join(git_root, "tools/test_harness/README.md"))
    readme_rel = os.path.relpath(readme_abs, run_dir)

    # Re-import results and calculate averages
    results = results_json["scenarios"]
    api_ttfts = []
    api_ttlts = []
    ui_ttfts = []
    ui_ttlts = []
    for s_name, s_data in results.items():
        for r in s_data["runs"]:
            if r.get("error"):
                continue
            if "ui" in r["api"].lower():
                if r.get("ttft") is not None:
                    ui_ttfts.append(r["ttft"])
                if r.get("ttlt") is not None:
                    ui_ttlts.append(r["ttlt"])
            else:
                if r.get("ttft") is not None:
                    api_ttfts.append(r["ttft"])
                if r.get("ttlt") is not None:
                    api_ttlts.append(r["ttlt"])
                    
    avg_api_ttft_val = sum(api_ttfts) / len(api_ttfts) if api_ttfts else None
    avg_api_ttlt_val = sum(api_ttlts) / len(api_ttlts) if api_ttlts else None
    avg_ui_ttft_val = sum(ui_ttfts) / len(ui_ttfts) if ui_ttfts else None
    avg_ui_ttlt_val = sum(ui_ttlts) / len(ui_ttlts) if ui_ttlts else None

    def fmt_avg(val):
        return f"`{val:.3f} s`" if val is not None else "`N/A`"

    # Group scenarios by base name
    from collections import defaultdict
    grouped = defaultdict(list)
    for s in scenarios:
        base_name = get_scenario_base_name(s["name"])
        grouped[base_name].append(s)

    # Helper to detect connectors
    def detect_connectors(scenario_name):
        connectors = []
        name_upper = scenario_name.upper()
        if "GDRIVE" in name_upper or "GOOGLE DRIVE" in name_upper or "HR EMPLOYEE HANDBOOK" in name_upper:
            connectors.append("Google Drive")
        if "CONFLUENCE" in name_upper:
            connectors.append("Confluence")
        if "JIRA" in name_upper:
            connectors.append("Jira")
        if "LUMAPPS" in name_upper or "GCS" in name_upper:
            connectors.append("LumApps (GCS)")
        if "3-WAY" in name_upper:
            connectors.extend(["LumApps (GCS)", "Confluence", "Jira"])
        if not connectors:
            connectors.append("Default Search Index")
        return list(set(connectors))

    scenarios_section = ""
    for base_name, group in grouped.items():
        first_s = group[0]
        s_query = first_s.get("query", query)
        complexity = first_s.get("complexity_level", "Unknown")
        expected_connectors = detect_connectors(base_name)
        
        flash_api = next((s for s in group if "3.5 flash" in s["name"].lower() and "ui" not in s["api"].lower()), None)
        flash_ui = next((s for s in group if "3.5 flash" in s["name"].lower() and "ui" in s["api"].lower()), None)
        pro_api = next((s for s in group if "3.1 pro" in s["name"].lower() and "ui" not in s["api"].lower()), None)
        pro_ui = next((s for s in group if "3.1 pro" in s["name"].lower() and "ui" in s["api"].lower()), None)
        
        def get_model_stats(s_dict):
            if not s_dict:
                return "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"
            s_name = s_dict["name"]
            # In results.json the key is the exact scenario name
            runs_data = results_json["scenarios"][s_name]["runs"]
            
            # import math stats
            # Since regenerate_report doesn't have get_stats defined, we can import it or define it.
            # Wait, get_stats is in chart_generator or we can import it.
            # In run_concurrent_benchmark it is defined locally, let's define a tiny helper or import it.
            # In regenerate_report, we can define a quick percentile helper!
            def get_stats_local(lst):
                if not lst:
                    return None, None, None, None, None, None, None
                sorted_lst = sorted(lst)
                n = len(sorted_lst)
                val_min = sorted_lst[0]
                val_max = sorted_lst[-1]
                val_avg = sum(sorted_lst) / n
                def pct(p):
                    idx = int(round(p * (n - 1)))
                    return sorted_lst[idx]
                return val_min, pct(0.5), pct(0.9), pct(0.95), pct(0.99), val_max, val_avg

            ttft_list = [r["ttft"] for r in runs_data if not r.get("error") and r.get("ttft") is not None]
            ttlt_list = [r["ttlt"] for r in runs_data if not r.get("error") and r.get("ttlt") is not None]
            ttft_min, ttft_p50, _, ttft_p95, _, ttft_max, _ = get_stats_local(ttft_list)
            ttlt_min, ttlt_p50, _, ttlt_p95, _, ttlt_max, _ = get_stats_local(ttlt_list)
            
            def fmt_val(val):
                return f"{val:.3f} s" if val is not None else "N/A"
            return fmt_val(ttft_min), fmt_val(ttft_p50), fmt_val(ttft_p95), fmt_val(ttft_max), fmt_val(ttlt_min), fmt_val(ttlt_p50), fmt_val(ttlt_p95), fmt_val(ttlt_max)

        f_api_ttft_min, f_api_ttft_p50, f_api_ttft_p95, f_api_ttft_max, f_api_ttlt_min, f_api_ttlt_p50, f_api_ttlt_p95, f_api_ttlt_max = get_model_stats(flash_api)
        f_ui_ttft_min, f_ui_ttft_p50, f_ui_ttft_p95, f_ui_ttft_max, f_ui_ttlt_min, f_ui_ttlt_p50, f_ui_ttlt_p95, f_ui_ttlt_max = get_model_stats(flash_ui)
        p_api_ttft_min, p_api_ttft_p50, p_api_ttft_p95, p_api_ttft_max, p_api_ttlt_min, p_api_ttlt_p50, p_api_ttlt_p95, p_api_ttlt_max = get_model_stats(pro_api)
        p_ui_ttft_min, p_ui_ttft_p50, p_ui_ttft_p95, p_ui_ttft_max, p_ui_ttlt_min, p_ui_ttlt_p50, p_ui_ttlt_p95, p_ui_ttlt_max = get_model_stats(pro_ui)
        
        # Build Detailed Invocations Rows
        run_rows = ""
        for i in range(1, iterations + 1):
            def get_run_row(s_dict, model_name, pathway_name, run_idx, is_first_row_for_run=False):
                run_cell = f"**{run_idx}**" if is_first_row_for_run else ""
                if not s_dict:
                    return ""
                s_name = s_dict["name"]
                runs_data = results_json["scenarios"][s_name]["runs"]
                run_data = next((r for r in runs_data if r["run_id"] == run_idx), None)
                if not run_data:
                    return ""
                
                if run_data.get("error"):
                    err_msg = run_data["error"].replace("\n", " ")[:60]
                    return f"| {run_cell} | {model_name} | {pathway_name} | {run_data['status_code']} | ERROR | ERROR | 0.0 | {err_msg} | N/A |\n"
                
                ttft_str = f"{run_data['ttft']:.3f}" if run_data.get('ttft') is not None else "N/A"
                ttlt_str = f"{run_data['ttlt']:.3f}" if run_data.get('ttlt') is not None else "N/A"
                speed_str = f"{run_data['generation_speed']:.1f}"
                
                if "ui" in s_dict["api"].lower():
                    screenshot_link = f"[Screenshot]({run_data['screenshot_path']})" if run_data.get('screenshot_path') else "N/A"
                    return f"| {run_cell} | {model_name} | UI (Preview) | {run_data['status_code']} | {ttft_str} | {ttlt_str} | {speed_str} | {screenshot_link} | N/A |\n"
                else:
                    trace_id_str = f"`{run_data['trace_id']}`" if run_data.get('trace_id') and run_data['trace_id'] != "N/A" else "N/A"
                    span_id_str = f"`{run_data['span_id']}`" if run_data.get('span_id') and run_data['span_id'] != "N/A" else "N/A"
                    return f"| {run_cell} | {model_name} | API (Stream) | {run_data['status_code']} | {ttft_str} | {ttlt_str} | {speed_str} | {trace_id_str} | {span_id_str} |\n"

            run_rows += get_run_row(flash_api, "Gemini 3.5 Flash", "API (Stream)", i, is_first_row_for_run=True)
            run_rows += get_run_row(flash_ui, "Gemini 3.5 Flash", "UI (Preview)", i, is_first_row_for_run=False)
            run_rows += get_run_row(pro_api, "Gemini 3.1 Pro", "API (Stream)", i, is_first_row_for_run=False)
            run_rows += get_run_row(pro_ui, "Gemini 3.1 Pro", "UI (Preview)", i, is_first_row_for_run=False)

        # Format scenario template
        scenario_md = scenario_template.format(
            scenario_name=base_name,
            complexity_level=f"`{complexity}` (Expected Connectors: {', '.join(expected_connectors)})",
            project_id=project_id,
            f_api_ttft_min=f_api_ttft_min, f_api_ttft_p50=f_api_ttft_p50, f_api_ttft_p95=f_api_ttft_p95, f_api_ttft_max=f_api_ttft_max,
            f_api_ttlt_min=f_api_ttlt_min, f_api_ttlt_p50=f_api_ttlt_p50, f_api_ttlt_p95=f_api_ttlt_p95, f_api_ttlt_max=f_api_ttlt_max,
            f_ui_ttft_min=f_ui_ttft_min, f_ui_ttft_p50=f_ui_ttft_p50, f_ui_ttft_p95=f_ui_ttft_p95, f_ui_ttft_max=f_ui_ttft_max,
            f_ui_ttlt_min=f_ui_ttlt_min, f_ui_ttlt_p50=f_ui_ttlt_p50, f_ui_ttlt_p95=f_ui_ttlt_p95, f_ui_ttlt_max=f_ui_ttlt_max,
            p_api_ttft_min=p_api_ttft_min, p_api_ttft_p50=p_api_ttft_p50, p_api_ttft_p95=p_api_ttft_p95, p_api_ttft_max=p_api_ttft_max,
            p_api_ttlt_min=p_api_ttlt_min, p_api_ttlt_p50=p_api_ttlt_p50, p_api_ttlt_p95=p_api_ttlt_p95, p_api_ttlt_max=p_api_ttlt_max,
            p_ui_ttft_min=p_ui_ttft_min, p_ui_ttft_p50=p_ui_ttft_p50, p_ui_ttft_p95=p_ui_ttft_p95, p_ui_ttft_max=p_ui_ttft_max,
            p_ui_ttlt_min=p_ui_ttlt_min, p_ui_ttlt_p50=p_ui_ttlt_p50, p_ui_ttlt_p95=p_ui_ttlt_p95, p_ui_ttlt_max=p_ui_ttlt_max,
            run_rows=run_rows
        )
        scenarios_section += scenario_md

    # Build Screenshots Section
    screenshots_section = "## 🖼️ Web App UI Run Screenshots\n\n"
    has_ui = False
    for s_name, s_data in results.items():
        if "ui" in s_name.lower():
            for r in s_data["runs"]:
                if r.get("screenshot_path"):
                    has_ui = True
                    screenshot_abs = os.path.abspath(os.path.join(run_dir, r['screenshot_path']))
                    screenshot_git_rel = os.path.relpath(screenshot_abs, git_root)
                    screenshots_section += screenshot_template.format(
                        run_id=r['run_id'],
                        scenario_name=s_name,
                        screenshot_path=r['screenshot_path'],
                        screenshot_path_git_rel=screenshot_git_rel
                    )
    if not has_ui:
        screenshots_section += "*No UI screenshots captured for this run.*\n\n"

    chart_path = chart_links.get('combined', '')
    duration_minutes = total_duration_s / 60.0
    
    # Format the master report
    final_report = report_template.format(
        report_title=report_title,
        timestamp=results_json['timestamp'],
        model_used=model_used,
        manifest_rel=copied_manifest_git_rel,
        readme_rel=readme_rel,
        run_dir=run_dir,
        manifest_filename=manifest_name,
        avg_api_ttft=fmt_avg(avg_api_ttft_val),
        avg_api_ttlt=fmt_avg(avg_api_ttlt_val),
        avg_ui_ttft=fmt_avg(avg_ui_ttft_val),
        avg_ui_ttlt=fmt_avg(avg_ui_ttlt_val),
        chart_path=chart_path,
        scenarios_section=scenarios_section,
        screenshots_section=screenshots_section,
        max_concurrency=max_concurrency,
        total_duration_s=total_duration_s,
        duration_minutes=duration_minutes,
        throughput_qpm=throughput_qpm
    )

    report_path = os.path.join(run_dir, "report.md")
    with open(report_path, "w") as rf:
        rf.write(final_report)
    print(f"Successfully regenerated combined report.md at: {report_path}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: uv run src/regenerate_report.py <run_dir>")
        sys.exit(1)
    regenerate(sys.argv[1])