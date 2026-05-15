"""
backend_core/utils/hf_sync.py — Download model artifacts from a private HF model repo.

Required env vars (set in .env locally, or in Render dashboard):
  HF_TOKEN    — your Hugging Face access token (read permission)
  HF_REPO_ID  — e.g. "Anjali3Mittal/Finstress-models"

Note: load_dotenv() must be called BEFORE this module is imported.
      server.py handles that at the very top.
"""

import os
import requests
from pathlib import Path
from backend_core.utils.logger import get_logger
from backend_core.config import MODELS_DIR

logger = get_logger("hf_sync", "logs/hf_sync.log")

# The three .pkl files that MUST exist for the app to work
_REQUIRED_PKLS = ["classifier.pkl", "clustering.pkl", "trend.pkl"]

# All files to download from the HF repo root
_ALL_FILES = [
    "classifier.pkl",
    "classifier_meta.json",
    "clustering.pkl",
    "clustering_meta.json",
    "trend.pkl",
    "trend_meta.json",
]


def _models_present() -> bool:
    """True only when all three core .pkl files exist on disk."""
    return all((MODELS_DIR / f).exists() for f in _REQUIRED_PKLS)


def sync_models() -> bool:
    """
    Download model artifacts from the private Hugging Face model repo.
    Tries snapshot_download first, falls back to direct HTTP download.
    Skips if the .pkl files are already on disk.
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

    logger.info(f"Models missing. Downloading from '{repo_id}' ...")

    # ── Strategy 1: snapshot_download (handles XetHub/LFS automatically) ──────
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=repo_id,
            repo_type="model",
            token=token,
            local_dir=str(MODELS_DIR),
            allow_patterns=["*.pkl", "*.json"],
            ignore_patterns=[".gitattributes", "README.md"],
        )
        if _models_present():
            logger.info("Model sync complete via snapshot_download.")
            return True
        logger.warning("snapshot_download finished but .pkl files still missing. Trying fallback...")
    except Exception as exc:
        logger.warning(f"snapshot_download failed ({exc}). Trying HTTP fallback...")

    # ── Strategy 2: Direct HTTP download from HF resolve endpoint ─────────────
    # URL pattern: https://huggingface.co/<repo_id>/resolve/main/<filename>
    return _http_download(repo_id, token)


def _http_download(repo_id: str, token: str) -> bool:
    """Download each model file individually using the HF HTTP API."""
    base_url = f"https://huggingface.co/{repo_id}/resolve/main"
    headers  = {"Authorization": f"Bearer {token}"}
    success  = True

    for filename in _ALL_FILES:
        dest = MODELS_DIR / filename
        if dest.exists():
            logger.info(f"  {filename} already exists, skipping.")
            continue

        url = f"{base_url}/{filename}"
        logger.info(f"  Downloading {filename} ...")
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=120)
            resp.raise_for_status()

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"  {filename} saved ({dest.stat().st_size / 1024:.1f} KB)")

        except Exception as e:
            logger.error(f"  Failed to download {filename}: {e}")
            success = False

    if _models_present():
        logger.info("Model sync complete via HTTP fallback.")
        return True
    else:
        missing = [f for f in _REQUIRED_PKLS if not (MODELS_DIR / f).exists()]
        logger.error(f"HTTP fallback done but still missing: {missing}")
        return False


# ── CLI: run directly to test sync ────────────────────────────────────────────
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    ok = sync_models()
    print("Result:", "SUCCESS" if ok else "FAILED -- check logs/hf_sync.log")
