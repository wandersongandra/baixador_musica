"""Router de arquivos: navegacao, download e upload."""

import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from hyperdl.core import splitter

router = APIRouter(prefix="/api/files", tags=["files"])

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "downloads" / "uploads"
CONTENT_DIRS = (BASE_DIR / "downloads", BASE_DIR / "separado")
MAX_UPLOAD_MB = 500


def safe_resolve(rel: str) -> Path:
    """Resolve um caminho relativo ou absoluto dentro de BASE_DIR."""
    p = Path(rel).expanduser()
    target = (BASE_DIR / p).resolve() if not p.is_absolute() else p.resolve()
    if target != BASE_DIR and BASE_DIR not in target.parents:
        raise HTTPException(403, "Caminho fora da area permitida")
    return target


def _ensure_content_file(target: Path):
    if not any(target == root or root in target.parents for root in CONTENT_DIRS):
        raise HTTPException(403, "Arquivo fora das areas de conteudo")


def sanitize_filename(name: str) -> str:
    name = Path(name or "arquivo").name
    name = re.sub(r'[^\w.\- ]', "_", name)
    return name.strip() or "arquivo"


def unique_path(dest: Path) -> Path:
    """Evita sobrescrever um upload anterior com o mesmo nome."""
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    for i in range(1, 1000):
        candidate = dest.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise HTTPException(409, "Nao foi possivel gerar nome unico para o arquivo")


@router.get("")
def list_files(rel: str = "", audio_only: bool = False):
    target = safe_resolve(rel)
    if not target.is_dir():
        raise HTTPException(404, "Diretorio nao encontrado")
    entries = []
    for child in sorted(target.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())):
        if child.name.startswith(".") or child.is_symlink():
            continue
        if (
            audio_only
            and not child.is_dir()
            and child.suffix.lower() not in splitter.AUDIO_EXTENSIONS
        ):
            continue
        try:
            st = child.stat()
        except OSError:
            continue
        entries.append(
            {
                "name": child.name,
                "path": str(child.relative_to(BASE_DIR)),
                "is_dir": child.is_dir(),
                "size": st.st_size if child.is_file() else 0,
                "modified": st.st_mtime,
            }
        )
    return {"dir": rel, "entries": entries}


@router.get("/download")
def download_file(path: str = Query(...)):
    target = safe_resolve(path)
    if not target.is_file():
        raise HTTPException(404, "Arquivo nao encontrado")
    _ensure_content_file(target)
    return FileResponse(target, filename=target.name)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    name = sanitize_filename(file.filename or "audio.bin")
    if Path(name).suffix.lower() not in splitter.AUDIO_EXTENSIONS:
        raise HTTPException(400, "Formato de audio nao suportado")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = unique_path(UPLOAD_DIR / name)
    name = dest.name
    bytes_written = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_MB * 1024 * 1024:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"Arquivo excede {MAX_UPLOAD_MB}MB")
            out.write(chunk)

    return {
        "name": name,
        "path": str(dest.relative_to(BASE_DIR)),
        "size": bytes_written,
    }
