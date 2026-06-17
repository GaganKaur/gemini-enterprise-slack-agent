import os
import json
import matplotlib.pyplot as plt
import numpy as np

def slugify(s):
    # Convert scenario name to a safe filename slug
    import re
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return s.strip('_')

def generate_charts_for_run(results_path, output_dir):
    print(f"Generating charts from: {results_path}")
    with open(results_path, "r") as f:
        data = json.load(f)
        
    charts_dir = os.path.join(output_dir, "charts")
    os.makedirs(charts_dir, exist_ok=True)
    
    # Configure matplotlib styles for high-fidelity report integration
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    generated_charts = {}
    
    for s_name, s_data in data.get("scenarios", {}).items():
        runs = s_data.get("runs", [])
        if not runs:
            continue
            
        run_ids = [r["run_id"] for r in runs]
        
        # Check if TTFT is present
        ttft_values = [r["ttft"] if r.get("ttft") is not None else r.get("ttft_s") for r in runs]
        ttlt_values = [r["ttlt"] if r.get("ttlt") is not None else r.get("ttlt_s") for r in runs]
        
        # Handle cases where all values are None (e.g. sync api doesn't have TTFT)
        has_ttft = any(v is not None for v in ttft_values)
        has_ttlt = any(v is not None for v in ttlt_values)
        
        s_slug = slugify(s_name)
        generated_charts[s_name] = {}
        
        # --- Chart 1: Latency by Run ID ---
        plt.figure(figsize=(8, 4.5))
        
        if has_ttlt:
            plt.plot(run_ids, ttlt_values, label="TTLT (Total Latency)", color="#e53935", marker="s", linewidth=2)
        if has_ttft:
            plt.plot(run_ids, ttft_values, label="TTFT (Time to First Token)", color="#1e88e5", marker="o", linewidth=2)
            
        plt.title(f"{s_name}\nLatency Across Runs", fontsize=12, fontweight="bold")
        plt.xlabel("Run ID", fontsize=10)
        plt.ylabel("Latency (seconds)", fontsize=10)
        plt.xticks(run_ids)
        plt.ylim(bottom=0)
        plt.legend(frameon=True, facecolor="white", edgecolor="none")
        plt.tight_layout()
        
        runs_chart_path = os.path.join(charts_dir, f"{s_slug}_runs.png")
        plt.savefig(runs_chart_path, dpi=150)
        plt.close()
        generated_charts[s_name]["runs_chart"] = os.path.relpath(runs_chart_path, output_dir)
        
        # --- Chart 2: Latency Histogram Bins ---
        plt.figure(figsize=(8, 4.5))
        
        # Define bins of 5 seconds: 0-5, 5-10, 10-15, 15-20, 20-25, 25-30, 30+
        bin_edges = [0, 5, 10, 15, 20, 25, 30, 35]
        bin_labels = ["0-5s", "5-10s", "10-15s", "15-20s", "20-25s", "25-30s", "30s+"]
        
        # Filter None values out
        valid_ttlt = [v for v in ttlt_values if v is not None]
        valid_ttft = [v for v in ttft_values if v is not None]
        
        # Clip max value to 34 to fall into 30-35 bin (which represents 30s+)
        clipped_ttlt = [min(v, 34.0) for v in valid_ttlt]
        clipped_ttft = [min(v, 34.0) for v in valid_ttft]
        
        # Calculate counts
        ttlt_counts, _ = np.histogram(clipped_ttlt, bins=bin_edges)
        ttft_counts, _ = np.histogram(clipped_ttft, bins=bin_edges)
        
        x = np.arange(len(bin_labels))
        width = 0.35
        
        if has_ttft and valid_ttft:
            plt.bar(x - width/2, ttft_counts, width, label="TTFT Counts", color="#42a5f5")
        if has_ttlt and valid_ttlt:
            plt.bar(x + width/2, ttlt_counts, width, label="TTLT Counts", color="#ef5350")
            
        plt.title(f"{s_name}\nLatency Distribution (5s Bins)", fontsize=12, fontweight="bold")
        plt.xlabel("Latency Interval", fontsize=10)
        plt.ylabel("Number of Responses", fontsize=10)
        plt.xticks(x, bin_labels)
        plt.ylim(bottom=0, top=max(max(ttlt_counts) if valid_ttlt else [0], max(ttft_counts) if valid_ttft else [0]) + 1)
        plt.legend(frameon=True, facecolor="white", edgecolor="none")
        plt.tight_layout()
        
        hist_chart_path = os.path.join(charts_dir, f"{s_slug}_histogram.png")
        plt.savefig(hist_chart_path, dpi=150)
        plt.close()
        generated_charts[s_name]["hist_chart"] = os.path.relpath(hist_chart_path, output_dir)
        
    # --- Generate Unified Latency Comparison Chart ---
    try:
        generate_combined_latency_comparison(results_path, charts_dir)
        # Store under a special key mapping relative to output_dir
        generated_charts["combined"] = os.path.relpath(os.path.join(charts_dir, "combined_latency_comparison.png"), output_dir)
    except Exception as e:
        print(f"Warning: Failed to generate combined comparison chart: {e}")
        
    return generated_charts

def generate_combined_latency_comparison(results_path, charts_dir):
    with open(results_path, "r") as f:
        data = json.load(f)
        
    scenarios = data.get("scenarios", {})
    if not scenarios:
        return
        
    labels = []
    ttft_avgs = []
    ttlt_avgs = []
    ttft_errs = []
    ttlt_errs = []
    
    for s_name, sc in scenarios.items():
        stats = sc["aggregated_stats"]
        ttft_avg = stats.get("ttft_avg_s")
        ttlt_avg = stats.get("ttlt_avg_s")
        
        runs = sc.get("runs", [])
        ttfts = [r["ttft"] if r.get("ttft") is not None else r.get("ttft_s") for r in runs]
        ttlts = [r["ttlt"] if r.get("ttlt") is not None else r.get("ttlt_s") for r in runs]
        
        ttfts = [v for v in ttfts if v is not None]
        ttlts = [v for v in ttlts if v is not None]
        
        # Simplify label text to prevent visual clutter
        short_label = s_name.replace("Scenario: ", "").replace("Assistant", "Asst").replace("14356008107232711696", "14356")
        labels.append(short_label)
        
        ttft_avgs.append(ttft_avg or 0.0)
        ttlt_avgs.append(ttlt_avg or 0.0)
        
        if ttfts and ttft_avg is not None:
            ttft_errs.append((ttft_avg - min(ttfts), max(ttfts) - ttft_avg))
        else:
            ttft_errs.append((0, 0))
            
        if ttlts and ttlt_avg is not None:
            ttlt_errs.append((ttlt_avg - min(ttlts), max(ttlts) - ttlt_avg))
        else:
            ttlt_errs.append((0, 0))
            
    ttft_err = np.array(ttft_errs).T
    ttlt_err = np.array(ttlt_errs).T
    
    x = np.arange(len(labels))
    width = 0.35
    
    # Scale width based on number of label scenarios
    fig_width = max(10, len(labels) * 1.8)
    fig, ax = plt.subplots(figsize=(fig_width, 6))
    
    rects1 = ax.bar(x - width/2, ttft_avgs, width, yerr=ttft_err, label='TTFT (Time to First Token)', 
                    color='#7bc0f7', edgecolor='#4588cc', capsize=4, error_kw={'ecolor': '#444', 'elinewidth': 1.2})
    rects2 = ax.bar(x + width/2, ttlt_avgs, width, yerr=ttlt_err, label='TTLT (Time to Last Token)', 
                    color='#305980', edgecolor='#1d3c5a', capsize=4, error_kw={'ecolor': '#444', 'elinewidth': 1.2})
    
    ax.set_ylabel('Latency (seconds)', fontsize=11, fontweight='semibold')
    ax.set_title('Unified Latency Performance Comparison (TTFT vs TTLT)\nacross all configured test scenarios', 
                 fontsize=13, fontweight='bold', pad=15)
    ax.set_xticks(x)
    
    rotation = 45 if len(labels) > 4 else 0
    ha = 'right' if rotation > 0 else 'center'
    ax.set_xticklabels(labels, fontsize=10, fontweight='semibold', rotation=rotation, ha=ha)
    
    ax.legend(frameon=True, facecolor='white', edgecolor='#e0e0e0', fontsize=10)
    
    max_val = max(ttlt_avgs) if ttlt_avgs else 0.0
    ax.set_ylim(0, max_val + max(5, max_val * 0.2))
    
    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            if height > 0:
                ax.annotate(f'{height:.1f}s',
                            xy=(rect.get_x() + rect.get_width() / 2, height),
                            xytext=(0, 2),
                            textcoords="offset points",
                            ha='center', va='bottom', fontsize=9, fontweight='semibold')
                            
    autolabel(rects1)
    autolabel(rects2)
    
    plt.tight_layout()
    out_path = os.path.join(charts_dir, "combined_latency_comparison.png")
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Generated unified latency comparison chart at: {out_path}")

if __name__ == '__main__':
    # Standalone verification
    import sys
    if len(sys.argv) > 2:
        generate_charts_for_run(sys.argv[1], sys.argv[2])
