"""
backend_core/utils/hf_sync.py — Download model artifacts from a private HF model repo.

Required env vars (set in .env or Render dashboard):
  HF_TOKEN    — your Hugging Face access token (read permission)
  HF_REPO_ID  — e.g. "Anjali3Mittal/Finstress-models"

Note: load_dotenv() must be called BEFORE this module is imported.
      server.py handles that at the very top.
"""

import os
from pathlib import Path
from huggingface_hub import snapshot_download
from backend_core.utils.logger import get_logger
from backend_core.config import MODELS_DIR

logger = get_logger("hf_sync", "logs/hf_sync.log")

# The three .pkl files that must exist for the app to work
_REQUIRED_PKLS = ["classifier.pkl", "clustering.pkl", "trend.pkl"]


def _models_present() -> bool:
    """True only when all three core model files exist on disk."""
    return all((MODELS_DIR / f).exists() for f in _REQUIRED_PKLS)


def sync_models() -> bool:
    """
    Download model artifacts from the private Hugging Face model repo.

    Skips download if the .pkl files are already on disk.
    Returns True on success, False on failure.
    """
    repo_id = os.getenv("HF_REPO_ID", "").strip()
    token   = os.getenv("HF_TOKEN",   "").strip()

    if not repo_id:
        logger.warning("HF_REPO_ID is not set — skipping model sync.")
        return False
    if not token:
        logger.warning("HF_TOKEN is not set — skipping model sync.")
        return False

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if _models_present():
        logger.info(f"Models already present in {MODELS_DIR} — skipping download.")
        return True

    logger.info(f"Downloading models from private repo '{repo_id}' ...")
    try:
        snapshot_download(
            repo_id=repo_id,
            repo_type="model",          # it's a model repo, not a Space
            token=token,
            local_dir=str(MODELS_DIR),
            allow_patterns=["*.pkl", "*.json", "*.csv"],
            ignore_patterns=[".gitattributes", "README.md"],
        )

        if _models_present():
            logger.info("Model sync complete.")
            return True
        else:
            missing = [f for f in _REQUIRED_PKLS if not (MODELS_DIR / f).exists()]
            logger.error(f"Sync finished but these files are still missing: {missing}")
            return False

    except Exception as exc:
        logger.error(f"Model sync failed: {exc}", exc_info=True)
        return False


# ── Quick test: run directly to verify sync works ─────────────────────────────
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    ok = sync_models()
    print("Result:", "SUCCESS" if ok else "FAILED -- check logs/hf_sync.log")
