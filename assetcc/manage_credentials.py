import argparse
import getpass
import json
import os
import tempfile

from werkzeug.security import generate_password_hash


def main():
    parser = argparse.ArgumentParser(
        description="Create or update a hashed fallback credential without echoing the password."
    )
    parser.add_argument("username")
    parser.add_argument("credentials_file")
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    if len(password) < 8:
        raise SystemExit("Password must contain at least 8 characters")

    credentials = {}
    if os.path.exists(args.credentials_file):
        with open(args.credentials_file, encoding="utf-8") as source:
            credentials = json.load(source)
        if not isinstance(credentials, dict):
            raise SystemExit("Credentials file must contain a JSON object")

    credentials[args.username.strip()] = generate_password_hash(password)
    destination = os.path.abspath(args.credentials_file)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    file_descriptor, temporary_path = tempfile.mkstemp(
        dir=os.path.dirname(destination), prefix=".credentials-", text=True
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as output:
            json.dump(credentials, output, indent=2)
            output.write("\n")
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, destination)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)

    print(f"Updated hashed credential for {args.username.strip()} in {destination}")


if __name__ == "__main__":
    main()
