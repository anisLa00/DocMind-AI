"""Safe storage of uploaded files on the local filesystem."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import UploadFile

from src.config import settings
from src.utils.errors import FileTooLargeError, UnsupportedFileTypeError

logger = logging.getLogger(__name__)

_READ_CHUNK = 1024 * 1024  # 1 MiB


class StorageService:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or settings.UPLOAD_DIR).resolve()

    def validate_filename(self, filename: str | None) -> str:
        """Check the extension against the allow-list and return it."""
        name = Path(filename or "").name
        suffix = Path(name).suffix.lower()

        if not suffix:
            raise UnsupportedFileTypeError("The uploaded file has no extension")
        if suffix not in settings.ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(settings.ALLOWED_EXTENSIONS))
            raise UnsupportedFileTypeError(
                f"Unsupported file type '{suffix}'. Allowed types: {allowed}"
            )

        return suffix

    def build_path(self, user_id: uuid.UUID, document_id: uuid.UUID, suffix: str) -> Path:
        """Stored name is derived from IDs only, so a hostile filename (path
        traversal, control characters, collisions) can never influence it."""
        return self.base_dir / str(user_id) / f"{document_id}{suffix}"

    async def save_upload(
        self, upload_file: UploadFile, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> tuple[Path, int]:
        """Stream an upload to disk, enforcing the size cap as we go."""
        suffix = self.validate_filename(upload_file.filename)
        destination = self.build_path(user_id, document_id, suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)

        max_bytes = settings.max_upload_size_bytes
        written = 0

        try:
            with destination.open("wb") as buffer:
                while data := await upload_file.read(_READ_CHUNK):
                    written += len(data)
                    if written > max_bytes:
                        raise FileTooLargeError(
                            f"File exceeds the maximum size of {settings.MAX_UPLOAD_SIZE_MB} MB"
                        )
                    buffer.write(data)
        except Exception:
            self.delete(destination)
            raise
        finally:
            await upload_file.close()

        if written == 0:
            self.delete(destination)
            raise FileTooLargeError("The uploaded file is empty")

        return destination, written

    def delete(self, file_path: str | Path | None) -> None:
        """Best-effort removal; a missing file is not an error."""
        if not file_path:
            return
        try:
            path = Path(file_path)
            path.unlink(missing_ok=True)
            parent = path.parent
            # Tidy up the per-user directory once its last document is gone.
            if parent != self.base_dir and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError as exc:  # pragma: no cover - filesystem specific
            logger.warning("Could not delete %s: %s", file_path, exc)
