"""Aplicacao FastAPI do Hyper Downloader."""

import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from hyperdl import APP_NAME, __version__
from hyperdl.api import files as files_api
from hyperdl.api.jobs import JobManager
from hyperdl.api.schemas import DownloadRequest, SettingsModel, SplitRequest
from hyperdl.core import downloader, splitter
from hyperdl.settings import settings

WEB_DIR = Path(__file__).resolve().parents[1] / "web" / "static"

app = FastAPI(title=f"{APP_NAME} Web", version=__version__)
jobs = JobManager()


def _get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job nao encontrado")
    return job


def _update_item(job: dict, url: str, **fields):
    for item in job["items"]:
        if item["url"] == url:
            item.update(fields)
            return
    job["items"].append({"url": url, **fields})


def _run_download_job(job: dict, req: DownloadRequest):
    cancel = job["cancel"]
    job["started"] = time.time()

    cfg = downloader.DownloadConfig(
        mode=downloader.DownloadMode(req.mode),
        audio_format=req.audio_format,
        audio_quality=req.audio_quality,
        video_quality=req.video_quality,
        output_dir=Path(req.output_dir),
        playlist=req.playlist,
        playlist_items=req.playlist_items,
        sponsorblock=req.sponsorblock,
        embed_metadata=req.embed_metadata,
        embed_thumbnail=req.embed_thumbnail,
        no_overwrites=req.no_overwrites,
        retries=req.retries,
        concurrent=req.concurrent,
        simulate=req.simulate,
    )

    def on_progress(p: downloader.DownloadProgress):
        job["progress"] = p.percent
        job["current"] = {
            "index": p.index,
            "total": p.total,
            "status": p.status,
            "title": p.title,
            "percent": p.percent,
            "downloaded": p.downloaded,
            "total_bytes": p.total_bytes,
            "speed": p.speed,
            "eta": p.eta,
            "error": p.error,
        }
        job["message"] = f"[{p.index}/{p.total}] {p.title or p.status}"
        if p.url:
            _update_item(
                job,
                p.url,
                status=p.status,
                title=p.title,
                percent=p.percent,
                error=p.error,
                filename=p.filename,
            )

    try:
        stats = downloader.download_urls(
            req.urls, cfg, on_progress, lambda: cancel.is_set()
        )
        job["stats"] = {
            "total": stats.total,
            "success": stats.success,
            "failed": stats.failed,
            "skipped": stats.skipped,
            "total_bytes": stats.total_bytes,
            "total_time": stats.total_time,
            "results": [
                {
                    "url": r.url,
                    "success": r.success,
                    "title": r.title,
                    "filename": r.filename,
                    "error": r.error,
                }
                for r in stats.results
            ],
        }
        if cancel.is_set():
            job["status"] = "cancelled"
            job["message"] = "Cancelado pelo usuario"
        elif stats.failed > 0:
            job["status"] = "completed"
            job["message"] = (
                f"Concluido com {stats.failed} falha(s): "
                f"{stats.success} ok, {stats.skipped} pulados"
            )
        else:
            job["status"] = "completed"
            job["message"] = (
                f"Concluido: {stats.success} ok, {stats.skipped} pulados"
            )
    except Exception as e:
        job["status"] = "failed"
        job["message"] = f"Erro interno: {e}"
    finally:
        job["finished"] = time.time()


def _run_split_job(job: dict, filepath: Path, cfg: splitter.SplitConfig):
    cancel = job["cancel"]
    job["started"] = time.time()

    def on_progress(pct: float, msg: str):
        job["progress"] = pct
        job["current"] = {"status": "processing", "title": msg, "percent": pct}
        job["message"] = f"Gerando {msg} ({pct:.0f}%)"

    try:
        result = splitter.split_file(
            filepath, cfg, on_progress, lambda: cancel.is_set()
        )
        job["result"] = {
            "input_file": str(result.input_file),
            "output_dir": str(result.output_dir) if result.output_dir else None,
            "tracks": [str(t) for t in result.tracks],
            "track_count": result.track_count,
            "segments_found": result.segments_found,
            "total_duration": result.total_duration,
            "error": result.error,
            "elapsed": result.elapsed,
        }
        if cancel.is_set():
            job["status"] = "cancelled"
            job["message"] = "Cancelado pelo usuario"
        elif result.error:
            job["status"] = "failed"
            job["message"] = result.error
        else:
            job["status"] = "completed"
            job["message"] = (
                f"{result.track_count} faixas geradas em {result.elapsed:.1f}s"
            )
    except Exception as e:
        job["status"] = "failed"
        job["message"] = f"Erro interno: {e}"
    finally:
        job["finished"] = time.time()


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": __version__,
        "ffmpeg": splitter.ensure_ffmpeg(),
        "yt_dlp": downloader.ensure_yt_dlp(),
    }


@app.get("/api/defaults")
def defaults():
    return {
        "audio_formats": sorted(downloader.AUDIO_FORMATS),
        "video_quals": sorted(downloader.VIDEO_QUALS),
        "split_formats": list(splitter.FORMAT_CODEC_MAP.keys()),
        "audio_quality": downloader.DEFAULT_AUDIO_QUAL,
        "video_quality": downloader.DEFAULT_VIDEO_QUAL,
        "max_upload_mb": 500,
    }


@app.get("/api/settings")
def get_settings():
    return {**SettingsModel().model_dump(), **settings.all()}


@app.put("/api/settings")
def update_settings(payload: SettingsModel):
    settings.update(payload.model_dump())
    return settings.all()


@app.post("/api/download")
def start_download(req: DownloadRequest):
    if not any(u.strip() for u in req.urls):
        raise HTTPException(400, "Informe ao menos uma URL")
    if req.mode not in ("audio", "video"):
        raise HTTPException(400, "Modo invalido: use 'audio' ou 'video'")
    if not downloader.ensure_yt_dlp():
        raise HTTPException(503, "yt-dlp nao instalado")
    job = jobs.create("download", output_dir=req.output_dir)
    job["urls"] = [u.strip() for u in req.urls if u.strip()]
    thread = threading.Thread(target=_run_download_job, args=(job, req), daemon=True)
    job["thread"] = thread
    thread.start()
    return {"id": job["id"]}


@app.post("/api/split")
def start_split(req: SplitRequest):
    p = Path(req.file).expanduser()
    if not p.is_absolute():
        p = files_api.BASE_DIR / p
    p = p.resolve()
    if not p.is_file():
        raise HTTPException(400, f"Arquivo nao encontrado: {req.file}")
    if p.suffix.lower() not in splitter.AUDIO_EXTENSIONS:
        raise HTTPException(400, "Formato de audio nao suportado")
    if not splitter.ensure_ffmpeg():
        raise HTTPException(503, "FFmpeg nao encontrado no PATH")

    cfg = splitter.SplitConfig(
        output_dir=Path(req.output_dir),
        threshold=req.threshold,
        min_silence=req.min_silence,
        min_track=req.min_track,
        lead_in=req.lead_in,
        lead_out=req.lead_out,
        fmt=req.fmt,
        prefix=req.prefix,
        digits=req.digits,
        adaptive=req.adaptive,
    )
    job = jobs.create("split", file=str(p), output_dir=req.output_dir)
    thread = threading.Thread(
        target=_run_split_job, args=(job, p, cfg), daemon=True
    )
    job["thread"] = thread
    thread.start()
    return {"id": job["id"]}


@app.get("/api/jobs")
def list_jobs():
    return {"jobs": [jobs.public(j) for j in jobs.list()]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return jobs.public(_get_job(job_id))


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = _get_job(job_id)
    if job["status"] in ("queued", "running"):
        job["cancel"].set()
        job["message"] = "Cancelando..."
    return {"id": job_id}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    if not jobs.delete(job_id):
        raise HTTPException(404, "Job nao encontrado")
    return {"ok": True}


app.include_router(files_api.router)
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="static")
