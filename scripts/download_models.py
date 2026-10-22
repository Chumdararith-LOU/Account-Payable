"""Download all model weights into models/ (one-time setup, network allowed).

Usage:
    python scripts/download_models.py

The runtime is fully offline; this script is the only step that needs the
network. It fetches:
  - PaddleOCR / PP-StructureV3 weights (14 models, ~1.2 GB) via PaddleX
  - Khmer OCR (TrorYongOCR, ~21 MB) from Hugging Face
  - Embedding model (MiniLM-L12-v2, ~476 MB) from Hugging Face

Cross-platform (Windows / Linux / macOS). Run inside the `anpr` env
(needs paddlex + huggingface_hub, both in requirements.txt). Already-present
models are skipped, so the script is safe to re-run.
"""

from __future__ import annotations

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS = REPO_ROOT / "models"

# PaddleOCR / PP-StructureV3 model subdirectories. Must match the values in
# apmatch/layout/structure.py::_MODEL_DIRS.
PADDLE_MODELS = (
    "PP-DocBlockLayout",
    "PP-DocLayout_plus-L",
    "PP-LCNet_x1_0_doc_ori",
    "PP-LCNet_x1_0_table_cls",
    "PP-LCNet_x1_0_textline_ori",
    "PP-OCRv5_server_det",
    "PP-OCRv5_server_rec",
    "PP-OCRv6_medium_det",
    "PP-OCRv6_medium_rec",
    "RT-DETR-L_wired_table_cell_det",
    "RT-DETR-L_wireless_table_cell_det",
    "SLANeXt_wired",
    "SLANet_plus",
    "UVDoc",
)

KHMER_REPO = "KrorngAI/TrorYongOCR"
EMBEDDINGS_REPO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDINGS_DIRNAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _copy_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, dirs_exist_ok=True)


def download_paddle() -> None:
    from paddlex.inference.utils.official_models import official_models

    dest_root = MODELS / "paddleocr"
    for name in PADDLE_MODELS:
        dest = dest_root / name
        if dest.is_dir() and any(dest.iterdir()):
            print(f"  [skip] {name} (already present)")
            continue
        print(f"  [fetch] {name} ...")
        src = Path(official_models.get_model_path(name))
        _copy_tree(src, dest)
    print(f"  Paddle models -> {dest_root}")


def download_hf(repo_id: str, dest: Path) -> None:
    from huggingface_hub import snapshot_download

    if dest.is_dir() and (dest / "model.safetensors").is_file():
        print(f"  [skip] {repo_id} (already present)")
        return
    print(f"  [fetch] {repo_id} ...")
    snapshot = Path(snapshot_download(repo_id))
    _copy_tree(snapshot, dest)
    print(f"  {repo_id} -> {dest}")


def main() -> None:
    print("PaddleOCR / PP-StructureV3 weights (~1.2 GB):")
    download_paddle()
    print("Khmer OCR (TrorYongOCR, ~21 MB):")
    download_hf(KHMER_REPO, MODELS / "khmer")
    print("Embedding model (MiniLM-L12-v2, ~476 MB):")
    download_hf(EMBEDDINGS_REPO, MODELS / "embeddings" / EMBEDDINGS_DIRNAME)
    print("\nDone. All model weights are in models/. The runtime is now fully offline.")


if __name__ == "__main__":
    main()
