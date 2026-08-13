from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.application.athlete_user_provisioning import AthleteUserProvisioningError, provision_athlete_user, validate_athlete_user_provisioning
from app.db.session import SessionLocal
from app.security.passwords import PasswordPolicyError


def _masked_email(value: str) -> str:
    local, separator, domain = value.partition("@")
    return f"{local[:1]}***{separator}{domain}" if separator else "***"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision a new User for an existing AthleteProfile.")
    parser.add_argument("--athlete-id", required=True, type=UUID)
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    return parser


def _show(preview) -> None:
    print(f"User:\n  email: {_masked_email(preview.normalized_email)}\n  display_name: {preview.display_name}")
    print(f"Membership:\n  Athlete: {preview.athlete_display_name}\n  role: athlete\n  active: true\n  default: true")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with SessionLocal() as session:
            preview = validate_athlete_user_provisioning(session, athlete_id=args.athlete_id, email=args.email, display_name=args.display_name, timezone=args.timezone)
            _show(preview)
            if args.dry_run:
                session.rollback()
                print("DRY-RUN: no database changes were made.")
                return 0
            if not args.yes and input("Type YES to continue: ") != "YES":
                session.rollback()
                print("Provisioning cancelled.")
                return 2
            password = getpass.getpass("Password: ")
            confirmation = getpass.getpass("Confirm password: ")
            if password != confirmation:
                session.rollback()
                print("password_confirmation_mismatch", file=sys.stderr)
                return 2
            provision_athlete_user(session, athlete_id=args.athlete_id, email=args.email, display_name=args.display_name, timezone=args.timezone, password=password)
            session.commit()
    except (AthleteUserProvisioningError, PasswordPolicyError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print("athlete_user_provisioning_failed", file=sys.stderr)
        return 1
    print("Athlete User provisioned successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
