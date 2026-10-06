"""Local account setup/reset. Does not start the web server or download workers."""

import argparse
from getpass import getpass

from app.config import Config
from app.services.auth import AccountStore


def main():
    parser = argparse.ArgumentParser(description="Manage your personal Reel account")
    parser.add_argument("command", choices=["set-user"])
    parser.parse_args()
    username = input("Username: ").strip()
    password = getpass("Password (at least 10 characters): ")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords do not match. Nothing was changed.")
    try:
        AccountStore(Config.AUTH_DATABASE).set_user(username, password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        "Account saved. Sign in with your username and password. Previous sessions are invalidated."
    )


if __name__ == "__main__":
    main()
