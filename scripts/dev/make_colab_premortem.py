import numpy as np
import json
from pathlib import Path

def generate():
    root = Path("data/fourcastnet_colab_upload_local")
    t = np.load(root / "input_tensor.npy")
    m = np.load(root / "global_means.npy")
    s = np.load(root / "global_stds.npy")
    
    # Simple z-score check
    m_slice = m[0, :20, 0, 0]
    s_slice = s[0, :20, 0, 0]
    t_means = np.mean(t, axis=(0, 2, 3))
    z_scores = (t_means - m_slice) / s_slice
    
    manifest = {
        "input_tensor": {
            "shape": list(t.shape),
            "dtype": str(t.dtype),
            "channel_means": t_means.tolist()
        },
        "stats": {
            "means_shape": list(m.shape),
            "stds_shape": list(s.shape),
            "z_score_means": z_scores.tolist()
        },
        "expected_channel_order": [
            "u10", "v10", "t2m", "sp", "msl", 
            "t850", "u1000", "v1000", "z1000", 
            "u850", "v850", "z850", 
            "u500", "v500", "z500", "t500", 
            "z50", "r500", "r850", "tcwv"
        ],
        "verdict": "PLAUSIBLE" if np.all(np.abs(z_scores) < 10) else "SUSPICIOUS"
    }
    
    with open(root / "premortem_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print("Generated premortem_manifest.json")

if __name__ == "__main__":
    generate()
