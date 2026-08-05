import hashlib
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

from app.config import Settings


@dataclass
class EncryptedCredentials:
    scheme: str
    enc_user: Optional[str]
    enc_password: Optional[str]
    enc_host: Optional[str]
    enc_port: Optional[str]
    enc_database: Optional[str]
    host_hash: str  # sha256(host) prefix — identity/reconnection groundwork
    display: str  # redacted, password masked — safe to return to clients


class CredentialCipher:
    def __init__(self, fernet: Fernet) -> None:
        self._f = fernet

    @classmethod
    def from_settings(cls, settings: Settings) -> tuple["CredentialCipher", bool]:
        """Return (cipher, ephemeral). Raises if a provided key is malformed."""
        key = settings.encryption_key.strip()
        if key:
            return cls(Fernet(key.encode())), False
        return cls(Fernet(Fernet.generate_key())), True

    #  part-level helpers
    def _enc(self, v: Optional[str]) -> Optional[str]:
        return self._f.encrypt(v.encode()).decode() if v is not None else None

    def _dec(self, tok: Optional[str]) -> Optional[str]:
        return self._f.decrypt(tok.encode()).decode() if tok is not None else None

    #  public API
    def encrypt(self, url: str) -> EncryptedCredentials:
        p = urlsplit(url)
        host = p.hostname or ""
        port = str(p.port) if p.port else None
        database = p.path.lstrip("/") or None
        host_hash = hashlib.sha256(host.encode()).hexdigest()[:16]
        display = (
            f"{p.scheme}://{p.username or ''}:***@{host}:{port or ''}/{database or ''}"
        )
        return EncryptedCredentials(
            scheme=p.scheme,
            enc_user=self._enc(p.username),
            enc_password=self._enc(p.password),
            enc_host=self._enc(host or None),
            enc_port=self._enc(port),
            enc_database=self._enc(database),
            host_hash=host_hash,
            display=display,
        )

    def decrypt_url(self, enc: EncryptedCredentials) -> str:
        user = self._dec(enc.enc_user)
        password = self._dec(enc.enc_password)
        host = self._dec(enc.enc_host) or ""
        port = self._dec(enc.enc_port)
        database = self._dec(enc.enc_database) or ""

        # urlsplit returns user/password already percent-encoded, so rebuild the
        # netloc verbatim (re-quoting would double-encode any '%').
        auth = ""
        if user is not None:
            auth = user
            if password is not None:
                auth += ":" + password
            auth += "@"
        netloc = f"{auth}{host}" + (f":{port}" if port else "")
        return f"{enc.scheme}://{netloc}/{database}"
