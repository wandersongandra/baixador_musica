"""Schemas Pydantic das requisicoes da API."""

from pydantic import BaseModel, Field, field_validator

from hyperdl.core import downloader, splitter

_AUDIO_QUALS = {str(i) for i in range(10)}


def _check_member(value: str, allowed: set[str], name: str) -> str:
    if value not in allowed:
        raise ValueError(f"{name} invalido: {value!r}")
    return value


class DownloadRequest(BaseModel):
    urls: list[str] = Field(min_length=1)
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
    retries: int = Field(default=downloader.DEFAULT_RETRIES, ge=0, le=50)
    concurrent: int = Field(default=downloader.DEFAULT_CONCURRENT, ge=1, le=16)
    simulate: bool = False

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in ("audio", "video"):
            raise ValueError("modo invalido: use 'audio' ou 'video'")
        return v

    @field_validator("audio_format")
    @classmethod
    def _audio_format(cls, v: str) -> str:
        return _check_member(v, downloader.AUDIO_FORMATS, "formato de audio")

    @field_validator("video_quality")
    @classmethod
    def _video_quality(cls, v: str) -> str:
        return _check_member(v, downloader.VIDEO_QUALS, "qualidade de video")

    @field_validator("audio_quality")
    @classmethod
    def _audio_quality(cls, v: str) -> str:
        return _check_member(v, _AUDIO_QUALS, "qualidade de audio (use 0-9)")


class SplitRequest(BaseModel):
    file: str = Field(min_length=1)
    output_dir: str = splitter.DEFAULT_OUTPUT_DIR
    threshold: str = splitter.DEFAULT_THRESHOLD
    min_silence: float = Field(default=splitter.DEFAULT_MIN_SILENCE, ge=0.1)
    min_track: float = Field(default=splitter.DEFAULT_MIN_TRACK, ge=1.0)
    lead_in: float = Field(default=splitter.DEFAULT_LEAD_IN, ge=0.0)
    lead_out: float = Field(default=splitter.DEFAULT_LEAD_OUT, ge=0.0)
    fmt: str = splitter.DEFAULT_FORMAT
    bitrate: str = Field(default="", pattern=r"^\d+[kKmM]?$|^$")
    prefix: str = splitter.DEFAULT_PREFIX
    digits: int = Field(default=splitter.DEFAULT_DIGITS, ge=1, le=4)
    adaptive: bool = False

    @field_validator("fmt")
    @classmethod
    def _fmt(cls, v: str) -> str:
        return _check_member(v, set(splitter.FORMAT_CODEC_MAP), "formato")


class SettingsModel(BaseModel):
    output_dir: str = "downloads"
    split_dir: str = splitter.DEFAULT_OUTPUT_DIR
    audio_format: str = downloader.DEFAULT_AUDIO_FMT
    video_quality: str = downloader.DEFAULT_VIDEO_QUAL
    threshold: str = splitter.DEFAULT_THRESHOLD
    min_silence: float = Field(default=splitter.DEFAULT_MIN_SILENCE, ge=0.1)
    min_track: float = Field(default=splitter.DEFAULT_MIN_TRACK, ge=1.0)
    split_fmt: str = splitter.DEFAULT_FORMAT
    split_prefix: str = splitter.DEFAULT_PREFIX
    playlist: bool = False
    sponsorblock: bool = False
    embed_metadata: bool = True
    embed_thumbnail: bool = True
    adaptive: bool = False

    @field_validator("audio_format")
    @classmethod
    def _audio_format(cls, v: str) -> str:
        return _check_member(v, downloader.AUDIO_FORMATS, "formato de audio")

    @field_validator("video_quality")
    @classmethod
    def _video_quality(cls, v: str) -> str:
        return _check_member(v, downloader.VIDEO_QUALS, "qualidade de video")

    @field_validator("split_fmt")
    @classmethod
    def _split_fmt(cls, v: str) -> str:
        return _check_member(v, set(splitter.FORMAT_CODEC_MAP), "formato")
