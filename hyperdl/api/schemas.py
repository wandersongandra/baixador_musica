"""Schemas Pydantic das requisicoes da API."""

from pydantic import BaseModel

from hyperdl.core import downloader, splitter


class DownloadRequest(BaseModel):
    urls: list[str]
    mode: str = "audio"
    audio_format: str = downloader.DEFAULT_AUDIO_FMT
    audio_quality: str = downloader.DEFAULT_AUDIO_QUAL
    video_quality: str = downloader.DEFAULT_VIDEO_QUAL
    output_dir: str = "downloads"
    playlist: bool = False
    playlist_items: str | None = None
    sponsorblock: bool = False
    embed_metadata: bool = True
    embed_thumbnail: bool = True
    no_overwrites: bool = True
    retries: int = downloader.DEFAULT_RETRIES
    concurrent: int = downloader.DEFAULT_CONCURRENT
    simulate: bool = False


class SplitRequest(BaseModel):
    file: str
    output_dir: str = splitter.DEFAULT_OUTPUT_DIR
    threshold: str = splitter.DEFAULT_THRESHOLD
    min_silence: float = splitter.DEFAULT_MIN_SILENCE
    min_track: float = splitter.DEFAULT_MIN_TRACK
    lead_in: float = splitter.DEFAULT_LEAD_IN
    lead_out: float = splitter.DEFAULT_LEAD_OUT
    fmt: str = splitter.DEFAULT_FORMAT
    prefix: str = splitter.DEFAULT_PREFIX
    digits: int = splitter.DEFAULT_DIGITS
    adaptive: bool = False


class SettingsModel(BaseModel):
    output_dir: str = "downloads"
    split_dir: str = splitter.DEFAULT_OUTPUT_DIR
    audio_format: str = downloader.DEFAULT_AUDIO_FMT
    video_quality: str = downloader.DEFAULT_VIDEO_QUAL
    threshold: str = splitter.DEFAULT_THRESHOLD
    min_silence: float = splitter.DEFAULT_MIN_SILENCE
    min_track: float = splitter.DEFAULT_MIN_TRACK
    split_fmt: str = splitter.DEFAULT_FORMAT
    split_prefix: str = splitter.DEFAULT_PREFIX
    playlist: bool = False
    sponsorblock: bool = False
    embed_metadata: bool = True
    embed_thumbnail: bool = True
    adaptive: bool = False
