"""Gerenciador de jobs (fila em memoria, com limite de retencao)."""

import threading
import time
import uuid

_ACTIVE = {"queued", "running"}


class JobManager:
    def __init__(self, max_jobs: int = 50):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._max = max_jobs

    def create(self, kind: str, **extra) -> dict:
        job = {
            "id": uuid.uuid4().hex[:12],
            "kind": kind,
            "status": "queued",
            "message": "Na fila...",
            "progress": 0.0,
            "created": time.time(),
            "started": None,
            "finished": None,
            "current": None,
            "items": [],
            "result": None,
            "stats": None,
            "cancel": threading.Event(),
            "thread": None,
            **extra,
        }
        with self._lock:
            self._jobs[job["id"]] = job
            self._trim()
        return job

    def _trim(self):
        if len(self._jobs) <= self._max:
            return
        ids = sorted(self._jobs, key=lambda k: self._jobs[k]["created"])
        for old in ids:
            if len(self._jobs) <= self._max:
                break
            if self._jobs[old]["status"] not in _ACTIVE:
                del self._jobs[old]

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 100) -> list[dict]:
        with self._lock:
            ids = sorted(
                self._jobs, key=lambda k: self._jobs[k]["created"], reverse=True
            )
            return [self._jobs[i] for i in ids[:limit]]

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job["status"] in _ACTIVE:
                job["cancel"].set()
            del self._jobs[job_id]
            return True

    @staticmethod
    def public(job: dict) -> dict:
        return {k: v for k, v in job.items() if k not in ("cancel", "thread")}
