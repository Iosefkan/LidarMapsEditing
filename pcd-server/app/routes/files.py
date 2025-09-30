import io
import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse

from ..storage import get_minio_client, ensure_bucket, presigned_get_object, upload_bytes
from ..settings import Settings, get_settings
from ..schemas import FileRecord, CleanRequest, CleanResponse
from ..worker import run_clean_process


router = APIRouter()


def get_db(settings: Settings):
    con = sqlite3.connect(settings.sqlite_path)
    con.row_factory = sqlite3.Row
    return con


def init_db(settings: Settings):
    os.makedirs(os.path.dirname(settings.sqlite_path), exist_ok=True)
    con = get_db(settings)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                content_type TEXT,
                size INTEGER,
                created_at TEXT NOT NULL,
                s3_key_original TEXT NOT NULL,
                s3_key_cleaned TEXT,
                s3_key_delta TEXT,
                summary_json TEXT
            )
            """
        )
        con.commit()
    finally:
        con.close()


@router.on_event("startup")
def on_startup():
    settings = get_settings()
    init_db(settings)
    client = get_minio_client(settings)
    ensure_bucket(client, settings.minio_bucket)


@router.post("/upload", response_model=FileRecord)
async def upload_file(file: UploadFile = File(...)):
    settings = get_settings()
    if not file.filename or not file.filename.lower().endswith(".pcd"):
        raise HTTPException(status_code=400, detail="Only .pcd files are supported")

    data = await file.read()
    file_id = str(uuid.uuid4())
    key = f"pcd/{file_id}/original/{file.filename}"

    client = get_minio_client(settings)
    upload_bytes(client, settings.minio_bucket, key, data, file.content_type or "application/octet-stream")

    con = get_db(settings)
    try:
        now = datetime.utcnow().isoformat()
        con.execute(
            "INSERT INTO files (id, filename, content_type, size, created_at, s3_key_original) VALUES (?,?,?,?,?,?)",
            (file_id, file.filename, file.content_type, len(data), now, key),
        )
        con.commit()
        rec = con.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    finally:
        con.close()

    url = presigned_get_object(client, settings.minio_bucket, key, expiry_seconds=3600)
    return FileRecord(
        id=file_id,
        filename=rec["filename"],
        size=rec["size"],
        created_at=rec["created_at"],
        original_url=url,
        cleaned_url=None,
        delta_url=None,
        summary=None,
    )


@router.get("/files", response_model=List[FileRecord])
def list_files():
    settings = get_settings()
    con = get_db(settings)
    try:
        rows = con.execute("SELECT * FROM files ORDER BY created_at DESC").fetchall()
    finally:
        con.close()
    out: List[FileRecord] = []
    for r in rows:
        original_url = f"/api/files/{r['id']}/original" if r["s3_key_original"] else None
        cleaned_url = f"/api/files/{r['id']}/cleaned" if r["s3_key_cleaned"] else None
        delta_url = f"/api/files/{r['id']}/delta" if r["s3_key_delta"] else None
        summary = json.loads(r["summary_json"]) if r["summary_json"] else None
        out.append(FileRecord(
            id=r["id"], filename=r["filename"], size=r["size"], created_at=r["created_at"],
            original_url=original_url, cleaned_url=cleaned_url, delta_url=delta_url, summary=summary
        ))
    return out


@router.get("/files/{file_id}", response_model=FileRecord)
def get_file(file_id: str):
    settings = get_settings()
    con = get_db(settings)
    try:
        r = con.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    finally:
        con.close()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    original_url = f"/api/files/{r['id']}/original" if r["s3_key_original"] else None
    cleaned_url = f"/api/files/{r['id']}/cleaned" if r["s3_key_cleaned"] else None
    delta_url = f"/api/files/{r['id']}/delta" if r["s3_key_delta"] else None
    summary = json.loads(r["summary_json"]) if r["summary_json"] else None
    return FileRecord(
        id=r["id"], filename=r["filename"], size=r["size"], created_at=r["created_at"],
        original_url=original_url, cleaned_url=cleaned_url, delta_url=delta_url, summary=summary
    )


@router.post("/files/{file_id}/clean", response_model=CleanResponse)
def clean_file(file_id: str, req: CleanRequest):
    settings = get_settings()
    # fetch db
    con = get_db(settings)
    try:
        r = con.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    finally:
        con.close()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")

    client = get_minio_client(settings)
    # download original to temp
    import minio
    tmpdir = tempfile.mkdtemp(prefix="pcd_")
    original_local = os.path.join(tmpdir, os.path.basename(r["s3_key_original"]))
    with open(original_local, "wb") as f:
        data = client.get_object(settings.minio_bucket, r["s3_key_original"]).read()
        f.write(data)

    cleaned_local = os.path.join(tmpdir, "cleaned.pcd")
    delta_local = os.path.join(tmpdir, "delta.pcd")
    # run cleaning directly
    summary = run_clean_process(original_local, cleaned_local, req, delta_out_path=delta_local)

    # prepare delta: points removed saved by algorithm as cleaned vs original; we will try reading optional removed file
    delta_key: Optional[str] = None
    if os.path.exists(delta_local):
        with open(delta_local, "rb") as f:
            delta_data = f.read()
        delta_key = f"pcd/{file_id}/delta/delta.pcd"
        upload_bytes(client, settings.minio_bucket, delta_key, delta_data, "application/octet-stream")

    # upload cleaned and summary
    with open(cleaned_local, "rb") as f:
        cleaned_data = f.read()
    cleaned_key = f"pcd/{file_id}/cleaned/cleaned.pcd"
    upload_bytes(client, settings.minio_bucket, cleaned_key, cleaned_data, "application/octet-stream")

    summary_key = f"pcd/{file_id}/cleaned/summary.json"
    upload_bytes(client, settings.minio_bucket, summary_key, json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"), "application/json")

    # update db
    con = get_db(settings)
    try:
        con.execute(
            "UPDATE files SET s3_key_cleaned=?, s3_key_delta=?, summary_json=? WHERE id=?",
            (cleaned_key, delta_key, json.dumps(summary, ensure_ascii=False), file_id),
        )
        con.commit()
    finally:
        con.close()

    cleaned_url = f"/api/files/{file_id}/cleaned"
    delta_url = f"/api/files/{file_id}/delta" if delta_key else None
    original_url = f"/api/files/{file_id}/original"

    return CleanResponse(
        id=file_id,
        original_url=original_url,
        cleaned_url=cleaned_url,
        delta_url=delta_url,
        summary=summary,
    )


def _stream_minio_object(bucket: str, key: str, filename: Optional[str] = None):
    settings = get_settings()
    client = get_minio_client(settings)
    response = client.get_object(bucket, key)
    try:
        import types
        from starlette.responses import StreamingResponse
        resolved_filename = filename or os.path.basename(key)
        def iterator():
            for d in response.stream(amt=8*1024):
                yield d
        return StreamingResponse(
            iterator(),
            media_type=response.getheader('Content-Type') or 'application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename="{resolved_filename}"'
            }
        )
    except Exception:
        response.close()
        response.release_conn()
        raise


@router.get("/files/{file_id}/original")
def download_original(file_id: str):
    settings = get_settings()
    con = get_db(settings)
    try:
        r = con.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    finally:
        con.close()
    if not r or not r["s3_key_original"]:
        raise HTTPException(status_code=404, detail="Not found")
    original_name = r["filename"] or "file.pcd"
    if not original_name.lower().endswith(".pcd"):
        original_name = f"{original_name}.pcd"
    return _stream_minio_object(settings.minio_bucket, r["s3_key_original"], filename=original_name)


@router.get("/files/{file_id}/cleaned")
def download_cleaned(file_id: str):
    settings = get_settings()
    con = get_db(settings)
    try:
        r = con.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    finally:
        con.close()
    if not r or not r["s3_key_cleaned"]:
        raise HTTPException(status_code=404, detail="Not found")
    base, _ = os.path.splitext((r["filename"] or "file").rstrip())
    cleaned_name = f"{base}_cleaned.pcd"
    return _stream_minio_object(settings.minio_bucket, r["s3_key_cleaned"], filename=cleaned_name)


@router.get("/parameters", response_class=PlainTextResponse)
def get_parameters_description():
    # Serve the Russian parameters description file if present; otherwise return a short text
    base_dir = os.path.dirname(os.path.dirname(__file__))
    candidates = [
        os.path.join(base_dir, "parameters_description.txt"),
        os.path.join(os.path.dirname(base_dir), "parameters_description.txt"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
    return "Описание параметров недоступно в этом сборочном образе."  # 200 OK fallback


@router.get("/files/{file_id}/delta")
def download_delta(file_id: str):
    settings = get_settings()
    con = get_db(settings)
    try:
        r = con.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    finally:
        con.close()
    if not r or not r["s3_key_delta"]:
        raise HTTPException(status_code=404, detail="Not found")
    base, _ = os.path.splitext((r["filename"] or "file").rstrip())
    delta_name = f"{base}_delta.pcd"
    return _stream_minio_object(settings.minio_bucket, r["s3_key_delta"], filename=delta_name)


@router.delete("/files/{file_id}", status_code=204)
def delete_file_and_data(file_id: str):
    settings = get_settings()
    # Ensure file exists
    con = get_db(settings)
    try:
        row = con.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")

    # Delete all S3 objects under this file's prefix
    client = get_minio_client(settings)
    prefix = f"pcd/{file_id}/"
    try:
        for obj in client.list_objects(settings.minio_bucket, prefix=prefix, recursive=True):
            try:
                client.remove_object(settings.minio_bucket, obj.object_name)
            except Exception:
                pass
    except Exception:
        # proceed to try to remove DB row regardless
        pass

    # Remove DB row
    con = get_db(settings)
    try:
        con.execute("DELETE FROM files WHERE id=?", (file_id,))
        con.commit()
    finally:
        con.close()

    return Response(status_code=204)


@router.post("/files/{file_id}/save_original", response_model=FileRecord)
async def save_original(file_id: str, file: UploadFile = File(...)):
    settings = get_settings()
    if not file.filename or not file.filename.lower().endswith(".pcd"):
        raise HTTPException(status_code=400, detail="Only .pcd files are supported")

    con = get_db(settings)
    try:
        r = con.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Not found")
    finally:
        con.close()

    data = await file.read()
    client = get_minio_client(settings)
    # Upload new original
    key = f"pcd/{file_id}/original/{file.filename}"
    upload_bytes(client, settings.minio_bucket, key, data, file.content_type or "application/octet-stream")

    # Update DB: set original, clear cleaned and delta because they are invalidated
    con = get_db(settings)
    try:
        now = datetime.utcnow().isoformat()
        con.execute(
            "UPDATE files SET filename=?, size=?, created_at=?, s3_key_original=?, s3_key_cleaned=NULL, s3_key_delta=NULL, summary_json=NULL WHERE id=?",
            (file.filename, len(data), now, key, file_id),
        )
        con.commit()
        r2 = con.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    finally:
        con.close()

    original_url = f"/api/files/{file_id}/original"
    cleaned_url = None
    delta_url = None
    return FileRecord(
        id=file_id,
        filename=r2["filename"],
        size=r2["size"],
        created_at=r2["created_at"],
        original_url=original_url,
        cleaned_url=cleaned_url,
        delta_url=delta_url,
        summary=None,
    )


@router.post("/files/{file_id}/save_cleaned", response_model=FileRecord)
async def save_cleaned(file_id: str, file: UploadFile = File(...)):
    settings = get_settings()
    if not file.filename or not file.filename.lower().endswith(".pcd"):
        raise HTTPException(status_code=400, detail="Only .pcd files are supported")

    con = get_db(settings)
    try:
        r = con.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Not found")
    finally:
        con.close()

    data = await file.read()
    client = get_minio_client(settings)
    # Upload new cleaned
    key = f"pcd/{file_id}/cleaned/{file.filename}"
    upload_bytes(client, settings.minio_bucket, key, data, file.content_type or "application/octet-stream")

    # Preserve delta when cleaned is replaced
    con = get_db(settings)
    try:
        con.execute(
            "UPDATE files SET s3_key_cleaned=? WHERE id=?",
            (key, file_id),
        )
        con.commit()
        r2 = con.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    finally:
        con.close()

    original_url = f"/api/files/{file_id}/original" if r2["s3_key_original"] else None
    cleaned_url = f"/api/files/{file_id}/cleaned"
    delta_url = f"/api/files/{file_id}/delta" if r2["s3_key_delta"] else None
    summary = json.loads(r2["summary_json"]) if r2["summary_json"] else None
    return FileRecord(
        id=file_id,
        filename=r2["filename"],
        size=r2["size"],
        created_at=r2["created_at"],
        original_url=original_url,
        cleaned_url=cleaned_url,
        delta_url=delta_url,
        summary=summary,
    )
