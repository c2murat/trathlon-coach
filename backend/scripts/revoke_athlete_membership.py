from __future__ import annotations

import argparse
import sys
from uuid import UUID

from app.application.athlete_membership_management import (
    AthleteMembershipRoleChangeError,
    revoke_athlete_membership,
    validate_athlete_membership_revocation,
)
from app.db.session import SessionLocal


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Revoke one Athlete membership safely.")
    value.add_argument("--user-id", type=UUID, required=True)
    value.add_argument("--athlete-id", type=UUID, required=True)
    value.add_argument("--dry-run", action="store_true")
    value.add_argument("--yes", action="store_true")
    return value


def _print(change, *, dry_run: bool) -> None:
    print(f"Athlete: {change.athlete_display_name} ({change.athlete_id})")
    print(f"User ID: {change.user_id}")
    print(f"Current role: {change.role}")
    print(f"Active: {str(change.was_active).lower()}")
    print(f"Default: {str(change.was_default).lower()}")
    print("Action: revoke")
    print(f"Controller after transition: {str(change.controller_after_transition).lower()}")
    if dry_run:
        print("No changes persisted.")
    elif change.changed:
        print("Membership revoked.")
    else:
        print("Membership already inactive; no changes required.")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.dry_run and not args.yes:
        print("Use --dry-run to preview or --yes to confirm.", file=sys.stderr)
        return 2
    session = SessionLocal()
    try:
        if args.dry_run:
            change = validate_athlete_membership_revocation(
                session, user_id=args.user_id, athlete_id=args.athlete_id
            )
            _print(change, dry_run=True)
            session.rollback()
        else:
            change = revoke_athlete_membership(
                session, user_id=args.user_id, athlete_id=args.athlete_id
            )
            session.commit()
            _print(change, dry_run=False)
        return 0
    except AthleteMembershipRoleChangeError as error:
        session.rollback()
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        session.rollback()
        print("athlete_membership_revocation_failed", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())