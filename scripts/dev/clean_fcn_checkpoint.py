import torch
from pathlib import Path

def clean_checkpoint():
    src = Path("data/fourcastnet_assets_v0/backbone.ckpt")
    dst = Path("data/fourcastnet_assets_v0/clean_backbone_weights.pt")
    
    if not src.exists():
        print(f"Error: {src} not found")
        return

    print(f"Loading {src} (weights_only=False for extraction)...")
    # We must use weights_only=False once to get the data out
    ckpt = torch.load(src, map_location="cpu")
    
    state_dict = ckpt['model_state'] if 'model_state' in ckpt else ckpt
    
    print(f"Saving clean state_dict to {dst}...")
    torch.save(state_dict, dst)
    print("Done. This file can now be loaded with weights_only=True.")

if __name__ == "__main__":
    clean_checkpoint()
