from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
os.chdir(repo_root)

os.environ["PROMPTLESS_YOUTUBE_ASR"] = "faster-whisper"
os.environ.setdefault("PROMPTLESS_YOUTUBE_ASR_MODEL", "tiny")
os.environ.setdefault("PROMPTLESS_YOUTUBE_ASR_MAX_SECONDS", "1800")
os.environ.setdefault("HF_HOME", str(repo_root / "data" / "huggingface"))

uvicorn.run("backend.app:app", host="127.0.0.1", port=8000)
