import json
from pathlib import Path

report_path = Path("data/fourcastnet_tensor_real_v1/tensor_validation_report_with_stats.json")
diag_json_path = Path("docs/fourcastnet/reports/stats_tensor_alignment_diagnostic.json")
diag_md_path = Path("docs/fourcastnet/reports/stats_tensor_alignment_diagnostic.md")

with open(report_path, "r") as f:
    report = json.load(f)

norm_stats = report["normalized_channel_stats"]
raw_stats = report["channel_stats"]

summary = {
    "abs_normalized_mean_gt_10": sum(1 for s in norm_stats if abs(s["mean"]) > 10),
    "abs_normalized_mean_gt_100": sum(1 for s in norm_stats if abs(s["mean"]) > 100),
    "abs_normalized_mean_gt_1000": sum(1 for s in norm_stats if abs(s["mean"]) > 1000),
}

worst_channels = sorted(norm_stats, key=lambda s: abs(s["mean"]), reverse=True)[:5]

diag_data = {
    "tensor_shape": report["shape"],
    "stats_metadata": report["means_metadata"],
    "summary": summary,
    "worst_channels": worst_channels,
    "all_channels": norm_stats
}

with open(diag_json_path, "w") as f:
    json.dump(diag_data, f, indent=2)

md_content = f"""# Stats/Tensor Alignment Diagnostic

## Summary
- **Policy**: {report["means_metadata"]["stats_channel_policy"]}
- **Tensor Order**: {report["means_metadata"]["tensor_channel_order"]}
- **Extreme Normalized Means (>10)**: {summary["abs_normalized_mean_gt_10"]}
- **Extreme Normalized Means (>100)**: {summary["abs_normalized_mean_gt_100"]}
- **Extreme Normalized Means (>1000)**: {summary["abs_normalized_mean_gt_1000"]}

## Top 5 Worst Channels (by abs normalized mean)
"""

for c in worst_channels:
    md_content += f"- Channel {c['channel_index']}: mean={c['mean']:.4f}, min={c['min']:.4f}, max={c['max']:.4f}\n"

md_content += "\n## Full Channel Table\n"
md_content += "| Index | Raw Mean | Stats Mean | Stats Std | Norm Mean | Norm Min | Norm Max |\n"
md_content += "|-------|----------|------------|-----------|-----------|----------|----------|\n"

# Note: Raw stats mean and used stats values would need more info than just what's in the report,
# but we can reconstruct Norm Mean from what we have.
for i, (r, n) in enumerate(zip(raw_stats, norm_stats)):
    md_content += f"| {i} | {r['mean']:.4f} | - | - | {n['mean']:.4f} | {n['min']:.4f} | {n['max']:.4f} |\n"

md_content += "\n## Verdict\n"
if summary["abs_normalized_mean_gt_10"] == 0:
    md_content += "**PLAUSIBLE**: All normalized means are within expected range (<10)."
else:
    md_content += "**SUSPICIOUS**: Some normalized means are still extreme."

with open(diag_md_path, "w") as f:
    f.write(md_content)

print(f"Generated {diag_json_path} and {diag_md_path}")
