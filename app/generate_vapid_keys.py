import argparse
import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def save_to_env(values: dict[str, str], *, force: bool) -> Path:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    existing_values = {
        key: line.split("=", 1)[1].strip()
        for key in values
        for line in lines
        if line.startswith(f"{key}=")
    }
    configured_keys = [
        key
        for key in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY")
        if existing_values.get(key)
    ]
    if configured_keys and not force:
        names = ", ".join(configured_keys)
        raise SystemExit(
            f"Przerwano: {names} ma już wartość w .env. "
            "Użyj --force tylko jeśli świadomie chcesz unieważnić istniejące subskrypcje."
        )
    values = dict(values)
    if existing_values.get("VAPID_SUBJECT") and not force:
        values["VAPID_SUBJECT"] = existing_values["VAPID_SUBJECT"]

    replaced: set[str] = set()
    updated_lines: list[str] = []
    for line in lines:
        matching_key = next((key for key in values if line.startswith(f"{key}=")), None)
        if matching_key:
            updated_lines.append(f"{matching_key}={values[matching_key]}")
            replaced.add(matching_key)
        else:
            updated_lines.append(line)

    missing_keys = [key for key in values if key not in replaced]
    if missing_keys:
        if updated_lines and updated_lines[-1]:
            updated_lines.append("")
        updated_lines.append("# Web Push (VAPID, bez Firebase)")
        updated_lines.extend(f"{key}={values[key]}" for key in missing_keys)

    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return env_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generuje stałą parę kluczy VAPID dla Web Push.")
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="zapisz wygenerowane wartości bezpośrednio do pliku .env",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="nadpisz istniejące klucze (unieważnia dotychczasowe subskrypcje)",
    )
    parser.add_argument(
        "--subject",
        default="mailto:admin@example.com",
        help="adres kontaktowy VAPID, np. mailto:admin@twojadomena.pl",
    )
    args = parser.parse_args()
    if not (
        (args.subject.startswith("mailto:") and "@" in args.subject)
        or args.subject.startswith("https://")
    ):
        parser.error("--subject musi być adresem mailto:... albo adresem https://...")

    private_key = ec.generate_private_key(ec.SECP256R1())
    private_value = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_value = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )

    values = {
        "VAPID_PUBLIC_KEY": base64url(public_value),
        "VAPID_PRIVATE_KEY": base64url(private_value),
        "VAPID_SUBJECT": args.subject,
    }
    if args.write_env:
        env_path = save_to_env(values, force=args.force)
        print(f"Zapisano klucze VAPID w {env_path}. Uruchom aplikację ponownie.")
        return

    print("Skopiuj poniższe wartości do pliku .env i nie zmieniaj ich po uruchomieniu push:")
    for key, value in values.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
