"""Motor de download de midia via yt-dlp."""

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from hyperdl.core.utils import ensure_ffmpeg, ensure_yt_dlp, format_bytes, format_duration

DEFAULT_OUTPUT_DIR = Path("downloads")
DEFAULT_TEMPLATE = "%(title).180s [%(id)s].%(ext)s"
DEFAULT_AUDIO_FMT = "mp3"
DEFAULT_AUDIO_QUAL = "0"
DEFAULT_VIDEO_QUAL = "best"
DEFAULT_RETRIES = 10
DEFAULT_CONCURRENT = 4

AUDIO_FORMATS = {"mp3", "m4a", "aac", "flac", "opus", "wav", "vorbis"}
VIDEO_QUALS = {"best", "360", "480", "720", "1080", "1440", "2160"}
BROWSER_LIST = {
    "brave", "chrome", "edge", "firefox", "opera", "safari", "vivaldi",
}


class DownloadMode(Enum):
    AUDIO = "audio"
    VIDEO = "video"


@dataclass
class DownloadConfig:
    mode: DownloadMode = DownloadMode.AUDIO
    audio_format: str = DEFAULT_AUDIO_FMT
    audio_quality: str = DEFAULT_AUDIO_QUAL
    video_quality: str = DEFAULT_VIDEO_QUAL
    output_dir: Path = DEFAULT_OUTPUT_DIR
    template: str = DEFAULT_TEMPLATE
    playlist: bool = False
    playlist_items: str | None = None
    cookies_from_browser: str | None = None
    cookies_file: Path | None = None
    proxy: str | None = None
    rate_limit: str | None = None
    retries: int = DEFAULT_RETRIES
    concurrent: int = DEFAULT_CONCURRENT
    no_overwrites: bool = True
    embed_metadata: bool = True
    embed_thumbnail: bool = True
    write_thumbnail: bool = False
    write_info_json: bool = False
    restrict_filenames: bool = True
    trim_filenames: int | None = None
    sponsorblock: bool = False
    archive: Path | None = None
    simulate: bool = False
    sleep_requests: float = 0.0
    sleep_interval: float = 0.0
    extractor_args: dict[str, str] | None = None
    verbose: bool = False


@dataclass
class DownloadResult:
    url: str
    success: bool
    title: str = ""
    filename: str | None = None
    filesize: int = 0
    error: str | None = None
    duration: float = 0.0


@dataclass
class DownloadStats:
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    total_bytes: int = 0
    total_time: float = 0.0
    start_time: float = field(default_factory=time.time)
    results: list[DownloadResult] = field(default_factory=list)


@dataclass
class DownloadProgress:
    url: str = ""
    index: int = 0
    total: int = 0
    status: str = "queued"
    percent: float = 0.0
    downloaded: int = 0
    total_bytes: int = 0
    speed: float = 0.0
    eta: float = 0.0
    title: str = ""
    filename: str | None = None
    error: str | None = None


ProgressCallback = Callable[[DownloadProgress], None]
CancelCheck = Callable[[], bool]


class DownloadArchive:
    def __init__(self, path: Path):
        self.path = path
        self._entries: set[str] = set()
        self._load()

    def _load(self):
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self._entries.add(line)

    def contains(self, vid: str) -> bool:
        return vid in self._entries

    def add(self, vid: str):
        if vid not in self._entries:
            self._entries.add(vid)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(f"{vid}\n")


def is_supported_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return True
    return url.startswith(("ytsearch", "plsearch", "ytdl"))


def is_playlist_url(url: str) -> bool:
    parsed = urlparse(url)
    return "list" in parse_qs(parsed.query)


def map_error(err_msg: str) -> str:
    if "Video unavailable" in err_msg or "Private video" in err_msg:
        return "Video indisponivel ou privado"
    if "Sign in" in err_msg:
        return "Necessita autenticacao (use cookies)"
    if "HTTP Error 429" in err_msg:
        return "Rate limited pelo YouTube (aguarde ou use proxy)"
    return err_msg


def build_ydl_opts(config: DownloadConfig) -> dict:
    opts: dict[str, Any] = {
        "outtmpl": str(config.output_dir / config.template),
        "restrictfilenames": config.restrict_filenames,
        "windowsfilenames": True,
        "continuedl": True,
        "overwrites": not config.no_overwrites,
        "retries": config.retries,
        "extractor_retries": config.retries,
        "fragment_retries": config.retries,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "no_color": True,
        "compat_opts": [],
    }

    if config.trim_filenames is not None:
        opts["trimfilenames"] = config.trim_filenames
    if config.cookies_from_browser:
        opts["cookiesfrombrowser"] = (config.cookies_from_browser,)
    if config.cookies_file:
        opts["cookiefile"] = str(config.cookies_file)
    if config.proxy:
        opts["proxy"] = config.proxy
    if config.rate_limit:
        opts["ratelimit"] = config.rate_limit
    if config.sleep_requests > 0:
        opts["sleep_requests"] = config.sleep_requests
    if config.sleep_interval > 0:
        opts["sleep_interval"] = config.sleep_interval
    if config.playlist:
        opts["yes_playlist"] = True
    else:
        opts["no_playlist"] = True
    if config.playlist_items:
        opts["playlist_items"] = config.playlist_items
    if config.simulate:
        opts["simulate"] = True
        opts["skip_download"] = True
    if config.archive:
        opts["download_archive"] = str(config.archive)
    if config.extractor_args:
        opts["extractor_args"] = config.extractor_args

    postprocessors: list[dict] = []

    if config.mode == DownloadMode.AUDIO:
        opts["format"] = "bestaudio/best"
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": config.audio_format,
                "preferredquality": config.audio_quality,
            }
        )
        if config.embed_metadata:
            postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})
        if config.embed_thumbnail:
            postprocessors.append(
                {
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": bool(config.write_thumbnail),
                }
            )
        if config.write_thumbnail:
            postprocessors.append(
                {"key": "FFmpegThumbnailsConvertor", "format": "jpg"}
            )
    else:
        opts["format"] = config.video_quality
        if config.embed_metadata:
            postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})
        if config.embed_thumbnail:
            postprocessors.append(
                {
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": bool(config.write_thumbnail),
                }
            )

    if config.sponsorblock:
        postprocessors += [
            {
                "key": "SponsorBlock",
                "categories": [
                    "sponsor", "intro", "outro", "selfpromo", "interaction",
                ],
            },
            {"key": "ModifyChapters", "remove_sponsor_segments": True},
        ]

    if postprocessors:
        opts["postprocessors"] = postprocessors

    if config.write_info_json:
        opts["writeinfojson"] = True

    return opts


def download_urls(
    urls: list[str],
    config: DownloadConfig,
    progress: ProgressCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> DownloadStats:
    import yt_dlp

    stats = DownloadStats(total=len(urls))
    archive = DownloadArchive(config.archive) if config.archive else None
    opts = build_ydl_opts(config)

    def emit(p: DownloadProgress):
        if progress:
            progress(p)

    def fail_url(url: str, msg: str, start: float):
        stats.failed += 1
        stats.results.append(
            DownloadResult(
                url=url,
                success=False,
                error=msg,
                duration=time.time() - start,
            )
        )
        emit(
            DownloadProgress(
                url=url,
                index=stats.success + stats.failed,
                total=stats.total,
                status="failed",
                title=url,
                error=msg,
            )
        )

    def download_item(url: str, start: float):
        dl_opts = dict(opts)
        if config.concurrent > 1:
            dl_opts["concurrent_fragment_downloads"] = config.concurrent

        def hook(d: dict):
            st = d.get("status")
            if st == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                down = d.get("downloaded_bytes", 0)
                emit(
                    DownloadProgress(
                        url=url,
                        index=stats.success + stats.failed + 1,
                        total=stats.total,
                        status="downloading",
                        percent=(down / total * 100) if total else 0.0,
                        downloaded=down,
                        total_bytes=total,
                        speed=d.get("speed") or 0,
                        eta=d.get("eta") or 0,
                        title=url,
                    )
                )
            elif st == "finished":
                emit(
                    DownloadProgress(
                        url=url,
                        index=stats.success + stats.failed + 1,
                        total=stats.total,
                        status="processing",
                        percent=100.0,
                        title=url,
                    )
                )

        dl_opts["progress_hooks"] = [hook]

        try:
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                info = ydl.extract_info(url, download=not config.simulate)

            if info is None:
                fail_url(url, "Nenhuma informacao obtida", start)
                return

            title = info.get("title") or info.get("id") or url
            filename: str | None = None
            try:
                filename = str(ydl.prepare_filename(info))
                if config.mode == DownloadMode.AUDIO:
                    filename = str(
                        Path(filename).with_suffix(f".{config.audio_format}")
                    )
            except Exception:
                pass

            fsize = info.get("filesize") or info.get("filesize_approx") or 0
            vid = info.get("id") or ""
            if archive and vid:
                archive.add(vid)

            stats.success += 1
            stats.total_bytes += fsize
            stats.results.append(
                DownloadResult(
                    url=url,
                    success=True,
                    title=title,
                    filename=filename,
                    filesize=fsize,
                    duration=time.time() - start,
                )
            )
            emit(
                DownloadProgress(
                    url=url,
                    index=stats.success + stats.failed,
                    total=stats.total,
                    status="finished",
                    percent=100.0,
                    title=title,
                    filename=filename,
                )
            )
        except yt_dlp.utils.DownloadError as e:
            fail_url(url, map_error(str(e)), start)
        except Exception as e:
            fail_url(url, str(e), start)

    for raw in urls:
        url = raw.strip()
        if is_cancelled and is_cancelled():
            break
        start = time.time()

        if not url or url.startswith("#"):
            stats.skipped += 1
            continue

        if not is_supported_url(url):
            fail_url(url, "URL invalida", start)
            continue

        if config.playlist and is_playlist_url(url):
            try:
                probe_opts = dict(opts)
                probe_opts.pop("progress_hooks", None)
                probe_opts["extract_flat"] = "in_playlist"
                with yt_dlp.YoutubeDL(probe_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                entries = list(filter(None, (info or {}).get("entries", []) or []))
            except Exception as e:
                fail_url(url, f"Falha ao ler playlist: {map_error(str(e))}", start)
                continue

            if not entries:
                fail_url(url, "Playlist vazia ou sem entradas", start)
                continue

            stats.total += len(entries) - 1
            for entry in entries:
                if is_cancelled and is_cancelled():
                    break
                if archive and entry.get("id") and archive.contains(entry["id"]):
                    stats.skipped += 1
                    continue
                e_url = entry.get("webpage_url") or (
                    f"https://www.youtube.com/watch?v={entry.get('id')}"
                )
                download_item(e_url, start)
        else:
            download_item(url, start)

    stats.total_time = time.time() - stats.start_time
    return stats
