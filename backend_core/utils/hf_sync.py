"""
src/utils/hf_sync.py - Sync models from private Hugging Face repo
"""

import os
import sys
from pathlib import Path
from huggingface_hub import snapshot_download
from backend_core.utils.logger import get_logger

logger = get_logger("hf_sync", "logs/hf_sync.log")

def sync_models():
    """
    Downloads models from a private HF repository if they are missing locally.
    Requires environment variables: HF_TOKEN, HF_REPO_ID
    """
    repo_id = os.getenv("HF_REPO_ID")
    token = os.getenv("HF_TOKEN")
    
    if not repo_id or not token:
        logger.warning("HF_REPO_ID or HF_TOKEN not found. Skipping model sync.")
        return False
        
    local_dir = Path("models")
    local_dir.mkdir(exist_ok=True)
    
    # Check if models already exist (heuristic: look for .pkl files)
    pkl_files = list(local_dir.glob("*.pkl"))
    if pkl_files:
        logger.info(f"Models already present in {local_dir}. Skipping download.")
        return True
        
    try:
        logger.info(f"Downloading models from private repo: {repo_id}...")
        snapshot_download(
            repo_id=repo_id,
            token=token,
            local_dir=str(local_dir),
            allow_patterns=["*.pkl", "*.json"],
            repo_type="model"
        )
        logger.info("Model sync complete.")
        return True
    except Exception as e:
        logger.error(f"Failed to sync models from Hugging Face: {e}")
        return False

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    sync_models()
