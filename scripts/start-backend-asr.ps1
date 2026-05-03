$ErrorActionPreference = "Stop"

$env:PROMPTLESS_YOUTUBE_ASR = "faster-whisper"
$env:PROMPTLESS_YOUTUBE_ASR_MODEL = if ($env:PROMPTLESS_YOUTUBE_ASR_MODEL) { $env:PROMPTLESS_YOUTUBE_ASR_MODEL } else { "tiny" }
$env:PROMPTLESS_YOUTUBE_ASR_MAX_SECONDS = if ($env:PROMPTLESS_YOUTUBE_ASR_MAX_SECONDS) { $env:PROMPTLESS_YOUTUBE_ASR_MAX_SECONDS } else { "1800" }

Set-Location (Resolve-Path "$PSScriptRoot\..")
& "C:\Users\alanq\AppData\Local\Programs\Python\Python311\python.exe" -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
