from __future__ import annotations
import argparse,json,re,sys
from collections import Counter
from pathlib import Path
from sqlalchemy import select
BACKEND_ROOT=Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:sys.path.insert(0,str(BACKEND_ROOT))
from app.core.settings import Settings,get_settings
from app.db.base import utc_now
from app.db.models import User,UserAuthSession
from app.db.session import SessionLocal
from app.security.passwords import password_hash_has_expected_format
HEX64=re.compile(r"^[0-9a-f]{64}$")
CHECK_NAMES=("invalid_lifetime","active_disabled_user","active_deleted_user","invalid_token_hash","invalid_csrf_hash","duplicate_token_hash","duplicate_csrf_hash","unexpected_password_hash","insecure_configuration")

def audit(session,*,settings:Settings,now=None)->dict:
    now=now or utc_now();issues={name:[] for name in CHECK_NAMES};sessions=list(session.scalars(select(UserAuthSession).order_by(UserAuthSession.id)).all());users={x.id:x for x in session.scalars(select(User)).all()}
    for row in sessions:
        item={"session_id":str(row.id)};active=row.revoked_at is None and row.expires_at>now;user=users.get(row.user_id)
        if row.expires_at<=row.created_at:issues["invalid_lifetime"].append(item)
        if active and user and user.status!="active":issues["active_disabled_user"].append(item)
        if active and user and user.deleted_at is not None:issues["active_deleted_user"].append(item)
        if not HEX64.fullmatch(row.token_hash):issues["invalid_token_hash"].append(item)
        if not HEX64.fullmatch(row.csrf_token_hash):issues["invalid_csrf_hash"].append(item)
    for field,name in (("token_hash","duplicate_token_hash"),("csrf_token_hash","duplicate_csrf_hash")):
        counts=Counter(getattr(x,field) for x in sessions);issues[name]=[{field:value,"count":count} for value,count in sorted(counts.items()) if count>1]
    issues["unexpected_password_hash"]=[{"user_id":str(x.id)} for x in sorted(users.values(),key=lambda x:str(x.id)) if x.password_hash is not None and not password_hash_has_expected_format(x.password_hash)]
    if settings.environment.casefold() in {"production","prod"} and settings.auth_mode=="session" and not settings.session_cookie_secure:issues["insecure_configuration"].append({"code":"session_cookie_not_secure"})
    return {"issue_count":sum(len(x) for x in issues.values()),"checks":issues}

def main(argv=None):
    parser=argparse.ArgumentParser(description="Auditoría de autenticación de solo lectura");parser.add_argument("--format",choices=("json","text"),default="text");args=parser.parse_args(argv)
    with SessionLocal() as session:result=audit(session,settings=get_settings());session.rollback()
    print(json.dumps(result,sort_keys=True,separators=(",",":")) if args.format=="json" else f"Errores de autenticación: {result['issue_count']}")
    return 1 if result["issue_count"] else 0
if __name__=="__main__":raise SystemExit(main())