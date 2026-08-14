from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.application.athlete_membership_management import AthleteMembershipRoleChangeError, set_athlete_membership_role, validate_athlete_membership_role_change
from app.db.models.membership import ATHLETE_MEMBERSHIP_ROLES
from app.db.session import SessionLocal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Change one existing Athlete membership role safely.")
    parser.add_argument("--user-id", required=True, type=UUID)
    parser.add_argument("--athlete-id", required=True, type=UUID)
    parser.add_argument("--role", required=True, choices=sorted(ATHLETE_MEMBERSHIP_ROLES))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    return parser


def _show(change, mode: str) -> None:
    print(f"User: {change.user_id}")
    print(f"Athlete: {change.athlete_display_name} ({change.athlete_id})")
    print(f"Current role: {change.current_role}")
    print(f"Requested role: {change.requested_role}")
    print(f"Active: {str(change.is_active).lower()}")
    print(f"Default: {str(change.is_default).lower()}")
    print(f"Controller after transition: {str(change.controller_after_transition).lower()}")
    print(f"Mode: {mode}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with SessionLocal() as session:
            preview = validate_athlete_membership_role_change(session, user_id=args.user_id, athlete_id=args.athlete_id, new_role=args.role)
            _show(preview, "dry-run" if args.dry_run else "change")
            if args.dry_run:
                session.rollback()
                print("No changes persisted.")
                return 0
            if not args.yes and input("Type YES to continue: ") != "YES":
                session.rollback()
                print("Role change cancelled.")
                return 2
            result = set_athlete_membership_role(session, user_id=args.user_id, athlete_id=args.athlete_id, new_role=args.role)
            session.commit()
    except AthleteMembershipRoleChangeError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print("athlete_membership_role_change_failed", file=sys.stderr)
        return 1
    print("Membership already in desired state." if not result.changed else "Membership role changed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
