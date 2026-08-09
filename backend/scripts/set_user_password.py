from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.models import User
from app.db.session import SessionLocal
from app.security.identity import normalize_email
from app.security.passwords import PasswordPolicyError, hash_password, validate_password


class UserPasswordBootstrapError(Exception):
    pass


def set_user_password(session: Session, *, email: str, password: str) -> None:
    validate_password(password)
    user = session.scalar(select(User).where(User.normalized_email == normalize_email(email)))
    if user is None:
        raise UserPasswordBootstrapError("User not found")
    user.password_hash = hash_password(password)
    session.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assign an initial password to an existing TriCoach user.")
    parser.add_argument("--email", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    password = getpass.getpass("Nueva contraseña: ")
    confirmation = getpass.getpass("Confirma la contraseña: ")
    if password != confirmation:
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return 2
    try:
        with SessionLocal() as session:
            set_user_password(session, email=args.email, password=password)
            session.commit()
    except PasswordPolicyError as error:
        print(str(error), file=sys.stderr)
        return 2
    except UserPasswordBootstrapError:
        print("Usuario no encontrado.", file=sys.stderr)
        return 1
    except Exception:
        print("No se pudo actualizar la contraseña.", file=sys.stderr)
        return 1
    print("Contraseña actualizada correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
