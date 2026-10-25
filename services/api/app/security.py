import hashlib
import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ApiKey, Project


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def create_raw_key() -> str:
    return f"ask_{secrets.token_urlsafe(32)}"


def issue_key(db: Session, project: Project, name: str = "default") -> tuple[ApiKey, str]:
    raw_key = create_raw_key()
    key = ApiKey(project_id=project.id, name=name, key_hash=hash_api_key(raw_key), prefix=raw_key[:12])
    db.add(key)
    db.flush()
    return key, raw_key


def project_for_key(db: Session, raw_key: str | None) -> Project | None:
    if not raw_key:
        return None
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw_key), ApiKey.revoked_at.is_(None)))
    return key.project if key else None


def revoke_key(key: ApiKey) -> None:
    key.revoked_at = datetime.utcnow()
