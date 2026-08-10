from __future__ import annotations
import argparse,json,sys
from datetime import timedelta
from pathlib import Path
from sqlalchemy import delete,or_,select
BACKEND_ROOT=Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:sys.path.insert(0,str(BACKEND_ROOT))
from app.core.settings import get_settings
from app.db.base import utc_now
from app.db.models import UserAuthSession
from app.db.session import SessionLocal

def eligible_session_ids(session,*,now,revoked_retention:timedelta):
    cutoff=now-revoked_retention
    return list(session.scalars(select(UserAuthSession.id).where(or_(UserAuthSession.expires_at<=now,UserAuthSession.revoked_at<=cutoff)).order_by(UserAuthSession.created_at,UserAuthSession.id)).all())

def cleanup_sessions(session,*,now,revoked_retention:timedelta,dry_run:bool)->dict:
    ids=eligible_session_ids(session,now=now,revoked_retention=revoked_retention)
    if not dry_run and ids:session.execute(delete(UserAuthSession).where(UserAuthSession.id.in_(ids)))
    return {"dry_run":dry_run,"eligible_count":len(ids),"deleted_count":0 if dry_run else len(ids),"session_ids":[str(value) for value in ids]}

def main(argv=None):
    parser=argparse.ArgumentParser(description="Cleanup seguro de sesiones de autenticación");mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument("--dry-run",action="store_true");mode.add_argument("--execute",action="store_true");parser.add_argument("--format",choices=("json","text"),default="text");args=parser.parse_args(argv)
    settings=get_settings()
    with SessionLocal() as session:
        result=cleanup_sessions(session,now=utc_now(),revoked_retention=timedelta(days=settings.revoked_session_retention_days),dry_run=args.dry_run)
        if args.execute:session.commit()
        else:session.rollback()
    print(json.dumps(result,sort_keys=True,separators=(",",":")) if args.format=="json" else f"Elegibles: {result['eligible_count']}; eliminadas: {result['deleted_count']}; dry_run: {result['dry_run']}")
    return 0
if __name__=="__main__":raise SystemExit(main())