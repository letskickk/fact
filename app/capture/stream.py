"""YouTube live stream audio capture.

Strategy: yt-dlp extracts HLS URL → ffmpeg records chunks directly.
This avoids pipe issues on Windows and works reliably with live streams.
"""

from __future__ import annotations

import asyncio
import glob as globmod
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import AsyncIterator

from app.config import settings

logger = logging.getLogger(__name__)

_WINGET_FFMPEG_GLOBS = [
    r"C:\Users\*\AppData\Local\Microsoft\WinGet\Packages\*FFmpeg*\*\bin\ffmpeg.exe",
]

_WINGET_DENO_GLOBS = [
    r"C:\Users\*\AppData\Local\Microsoft\WinGet\Packages\*Deno*\deno.exe",
]


def _find_tool(name: str, globs: list[str]) -> str:
    found = shutil.which(name)
    if found:
        return found
    if sys.platform == "win32":
        for pattern in globs:
            matches = globmod.glob(pattern)
            if matches:
                return matches[0]
    raise FileNotFoundError(f"{name} not found")


def _get_env() -> dict:
    """Build env dict with deno and ffmpeg directories on PATH."""
    env = os.environ.copy()
    extra_dirs = []
    for globs in [_WINGET_DENO_GLOBS, _WINGET_FFMPEG_GLOBS]:
        for pattern in globs:
            for match in globmod.glob(pattern):
                extra_dirs.append(str(Path(match).parent))
    if extra_dirs:
        env["PATH"] = ";".join(extra_dirs) + ";" + env.get("PATH", "")
    return env


def _get_stream_url(youtube_url: str, env: dict) -> str:
    """Use yt-dlp to extract the HLS stream URL."""
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--remote-components", "ejs:github",
        "-f", "91",  # lowest quality with audio (fast)
        "-g",         # print URL only
    ]
    if settings.youtube_cookies_file:
        cmd += ["--cookies", settings.youtube_cookies_file]
    cmd.append(youtube_url)
    logger.info("Getting stream URL: %s", youtube_url)
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {r.stderr[:300]}")
    url = r.stdout.strip()
    if not url:
        raise RuntimeError("yt-dlp returned empty URL")
    logger.info("Got HLS URL (length=%d)", len(url))
    return url


def _record_chunk(
    ffmpeg_path: str,
    stream_url: str,
    output_path: str,
    duration: int,
    env: dict,
) -> bool:
    """Record a single audio chunk from HLS stream using ffmpeg."""
    proc = subprocess.Popen(
        [
            ffmpeg_path,
            "-hide_banner", "-loglevel", "warning",
            "-i", stream_url,
            "-t", str(duration),
            "-vn",
            "-ac", "1", "-ar", "16000",
            "-acodec", "pcm_s16le",
            "-y", output_path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _, stderr = proc.communicate(timeout=duration * 12 + 60)
        if proc.returncode != 0:
            logger.warning("ffmpeg error: %s", stderr.decode(errors="replace")[:200])
            return False
        return Path(output_path).exists() and Path(output_path).stat().st_size > 1000
    except subprocess.TimeoutExpired:
        proc.kill()
        logger.warning("ffmpeg timeout recording chunk")
        return False


async def capture_audio_chunks(
    youtube_url: str,
    chunk_duration: int | None = None,
    output_dir: Path | None = None,
) -> AsyncIterator[Path]:
    """Yield WAV file paths, each containing `chunk_duration` seconds of live audio."""
    duration = chunk_duration or settings.chunk_duration
    workdir = output_dir or Path(tempfile.mkdtemp(prefix="fact_"))
    workdir.mkdir(parents=True, exist_ok=True)

    env = _get_env()
    ffmpeg_path = settings.ffmpeg_path or _find_tool("ffmpeg", _WINGET_FFMPEG_GLOBS)

    logger.info("Starting stream capture: %s (chunk=%ds)", youtube_url, duration)

    # Get HLS URL (refreshed periodically as tokens expire)
    stream_url = await asyncio.to_thread(_get_stream_url, youtube_url, env)

    chunk_index = 0
    url_refresh_interval = 20  # refresh URL every N chunks (tokens expire)

    try:
        while True:
            # Refresh stream URL periodically
            if chunk_index > 0 and chunk_index % url_refresh_interval == 0:
                try:
                    stream_url = await asyncio.to_thread(
                        _get_stream_url, youtube_url, env
                    )
                except Exception as e:
                    logger.warning("URL refresh failed: %s", e)

            chunk_path = workdir / f"chunk_{chunk_index:04d}.wav"

            logger.info("Recording chunk %d...", chunk_index)
            ok = await asyncio.to_thread(
                _record_chunk, ffmpeg_path, stream_url,
                str(chunk_path), duration, env
            )

            if ok:
                logger.info("Chunk %d ready (%d bytes)",
                            chunk_index, chunk_path.stat().st_size)
                yield chunk_path
                chunk_index += 1

                # Clean up previous chunk to save disk
                prev = workdir / f"chunk_{chunk_index - 2:04d}.wav"
                if prev.exists():
                    prev.unlink(missing_ok=True)
            else:
                logger.error("Failed to record chunk %d, stopping", chunk_index)
                break

    except asyncio.CancelledError:
        logger.info("Stream capture cancelled")
    finally:
        logger.info("Stream capture stopped (chunks: %d)", chunk_index)
