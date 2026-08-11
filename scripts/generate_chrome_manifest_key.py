from __future__ import annotations

from base64 import b64encode
from pathlib import Path
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_KEY_PATH = ROOT / "work" / "chrome-extension-key.pem"
MANIFEST_PATH = ROOT / "extension" / "manifest.chrome.json"


def main() -> int:
    PRIVATE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)

    if PRIVATE_KEY_PATH.exists():
        private_key = serialization.load_pem_private_key(PRIVATE_KEY_PATH.read_bytes(), password=None)
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        PRIVATE_KEY_PATH.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    public_der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    manifest_key = b64encode(public_der).decode("ascii")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["key"] = manifest_key
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Updated Chrome manifest key")
    print(PRIVATE_KEY_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
