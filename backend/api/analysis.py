from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone
import json
import io

from ..db import get_db
from ..models.user import User
from ..models.evidence import Evidence, EvidenceFile
from ..models.transfer import Custody
from ..models.analysis import Analysis, AnalysisFile
from ..models.audit import AuditLog
from ..schemas.analysis import AnalysisCreate, AnalysisResponse, AnalysisListResponse
from ..api.auth import get_current_user
from ..core.crypto import encrypt_file_data, decrypt_file_data, compute_sha256
from ..core.audit import create_audit_entry

router = APIRouter()


def _is_current_custodian(db: Session, evidence_id: int, user_id: int) -> bool:
    custody = db.query(Custody).filter(Custody.evidence_id == evidence_id).first()
    return bool(custody and custody.current_user_id == user_id)


@router.get("/by-evidence/{evidence_id}", response_model=AnalysisListResponse)
def list_analyses_for_evidence(
    evidence_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Ensure evidence exists
    ev = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

    # Anyone who can view evidence can view analyses; reuse evidence view rules indirectly
    # Evidence view is enforced elsewhere, but we ensure evidence exists and later hide downloads
    analyses = db.query(Analysis).filter(Analysis.evidence_id == evidence_id).order_by(Analysis.id.asc()).all()

    items: List[AnalysisResponse] = []
    for a in analyses:
        resp = AnalysisResponse.from_orm(a)
        # attach files
        resp.files = [
            {
                "id": f.id,
                "orig_filename": f.orig_filename,
                "mime": f.mime,
                "size_bytes": f.size_bytes,
                "sha256_hex": f.sha256_hex,
                "created_at_utc": f.created_at_utc,
            }
            for f in a.files
        ]
        items.append(resp) 
    return AnalysisListResponse(items=items, total=len(items))


@router.post("/", response_model=AnalysisResponse)
async def create_analysis(
    evidence_id: int = Form(...),
    analysis_at_iso: str = Form(...),
    analysis_by: str = Form(...),
    role: str = Form(...),
    place_of_analysis: str = Form(...),
    description: str = Form(...),
    files: List[UploadFile] = File([]),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Validate evidence
    ev = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

    # Only current custodian may add analysis
    if not _is_current_custodian(db, evidence_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only current custodian can add analysis")

    # Parse timestamp
    try:
        at_dt = datetime.fromisoformat(analysis_at_iso.replace("Z", "+00:00"))
        if at_dt.tzinfo is None:
            at_dt = at_dt.replace(tzinfo=timezone.utc)
        at_dt = at_dt.astimezone(timezone.utc).replace(microsecond=0)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid analysis_at_iso")

    analysis = Analysis(
        evidence_id=evidence_id,
        analysis_at_utc=at_dt,
        analysis_by=analysis_by,
        role=role,
        place_of_analysis=place_of_analysis,
        description=description,
        created_by_user_id=current_user.id,
    )
    db.add(analysis)
    db.flush()

    # Save files (encrypted)
    for uf in files or []:
        content = await uf.read()
        # encrypt_file_data returns (cipher_filename, sha256_hex)
        cipher_filename, sha = encrypt_file_data(content)
        af = AnalysisFile(
            analysis_id=analysis.id,
            orig_filename=uf.filename,
            mime=uf.content_type or "application/octet-stream",
            size_bytes=len(content),
            sha256_hex=sha,
            cipher_path=cipher_filename,
        )
        db.add(af)

    # Audit
    prev = db.query(AuditLog).filter(AuditLog.evidence_id == evidence_id).order_by(AuditLog.id.desc()).first()
    prev_hash = prev.entry_hash_hex if prev else ""
    details = {
        "action": "ANALYSIS_CREATED",
        "analysis_id": analysis.id,
        "analysis_by": analysis_by,
        "role": role,
        "place_of_analysis": place_of_analysis,
    }
    entry = create_audit_entry(
        evidence_id=evidence_id,
        actor_user_id=current_user.id,
        action="ANALYSIS_CREATED",
        details=details,
        prev_hash=prev_hash,
    )
    audit_log = AuditLog(
        evidence_id=evidence_id,
        actor_user_id=current_user.id,
        action=entry["action"],
        details_json=json.dumps(entry["details"]),
        ts_utc=datetime.fromisoformat(entry["ts_utc"]),
        prev_hash_hex=entry["prev_hash_hex"],
        entry_hash_hex=entry["entry_hash_hex"],
    )
    db.add(audit_log)

    db.commit()
    db.refresh(analysis)

    resp = AnalysisResponse.from_orm(analysis)
    resp.files = []
    return resp


@router.get("/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    a = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not a:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    # Viewing allowed for anyone who can view the parent evidence; we assume prior evidence checks on UI
    files = db.query(AnalysisFile).filter(AnalysisFile.analysis_id == a.id).all()
    resp = AnalysisResponse.from_orm(a)
    resp.files = [
        {
            "id": f.id,
            "orig_filename": f.orig_filename,
            "mime": f.mime,
            "size_bytes": f.size_bytes,
            "sha256_hex": f.sha256_hex,
            "created_at_utc": f.created_at_utc,
        }
        for f in files
    ]
    return resp


@router.get("/{analysis_id}/download/{file_id}")
async def download_analysis_file(
    analysis_id: int,
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    a = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not a:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    # Only current custodian of the parent evidence may download
    if not _is_current_custodian(db, a.evidence_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only current custodian can download analysis files")

    f = db.query(AnalysisFile).filter(AnalysisFile.id == file_id, AnalysisFile.analysis_id == analysis_id).first()
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    try:
        decrypted = decrypt_file_data(f.cipher_path)
        return StreamingResponse(
            io.BytesIO(decrypted),
            media_type=f.mime,
            headers={"Content-Disposition": f"attachment; filename={f.orig_filename}"}
        )
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Encrypted file not found on disk")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to decrypt file: {str(e)}")
