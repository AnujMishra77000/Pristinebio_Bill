"""Create private VPS settings once; never print secrets or replace an existing file."""
import argparse
import base64
import os
from pathlib import Path
import secrets


def create_env(output: Path) -> None:
    password = secrets.token_urlsafe(32)
    generated = {
        "POSTGRES_PASSWORD": password,
        "DATABASE_URL": f"postgresql+psycopg://pristine_billing:{password}@postgres:5432/pristine_billing",
        "JWT_SECRET_KEY": secrets.token_urlsafe(48),
        "MFA_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    }
    template = Path(__file__).with_name(".env.example").read_text()
    lines = []
    for line in template.splitlines():
        key, separator, _ = line.partition("=")
        lines.append(f"{key}={generated[key]}" if separator and key in generated else line)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".env.production"))
    arguments = parser.parse_args()
    try:
        create_env(arguments.output)
    except FileExistsError:
        parser.exit(1, "Settings already exist. Keep the existing credentials for subsequent releases.\n")
    print(f"Created private settings at {arguments.output}. Keep this file and its credentials for future releases.")
