"""Command line for accounts, run inside the API container.

    python -m apmatch.auth create-user <username> "<Display Name>" [--admin]
    python -m apmatch.auth reset-password <username>

Both print a one-time temporary password; the person must change it at first
sign-in. Passwords are never taken as arguments (they would land in shell
history).
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apmatch.auth.passwords import temporary_password
from apmatch.auth.service import AuthError, create_user, get_user, set_password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m apmatch.auth")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create-user", help="add a person who can sign in")
    c.add_argument("username")
    c.add_argument("display_name")
    c.add_argument("--admin", action="store_true", help="can add and manage users")
    r = sub.add_parser("reset-password", help="give a user a new temporary password")
    r.add_argument("username")
    args = parser.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    password = temporary_password()
    with Session(create_engine(url)) as session:
        try:
            if args.command == "create-user":
                user = create_user(
                    session,
                    args.username,
                    args.display_name,
                    password,
                    role="admin" if args.admin else "reviewer",
                )
            else:
                user = get_user(session, args.username)
                set_password(session, user, password, must_change=True)
            username, role = user.username, user.role
            session.commit()
        except (AuthError, ValueError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
    print(f"user: {username} ({role})")
    print(f"temporary password: {password}")
    print("They must choose a new password at first sign-in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
