from __future__ import annotations

import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from app.core.exceptions import AppException


_MIME_BY_TYPE = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_TYPE_BY_EXTENSION = {".pdf": "pdf", ".docx": "docx", ".pptx": "pptx"}
_MAX_ARCHIVE_ENTRIES = 10_000
_MAX_ARCHIVE_COMPRESSION_RATIO = 100
_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 128 * 1024 * 1024


class MaterialUploadValidationError(AppException):
    """A safe, client-actionable material upload validation failure."""


@dataclass(frozen=True)
class ValidatedMaterialUpload:
    file_type: str
    content_type: str
    size_bytes: int


def validate_material_upload(
    source: Path,
    *,
    filename: str,
    declared_content_type: str | None,
    max_size_bytes: int,
    max_archive_uncompressed_bytes: int | None = None,
) -> ValidatedMaterialUpload:
    """Validate a fully streamed temporary upload before object storage writes."""
    file_type = infer_material_file_type(filename)

    expected_content_type = _MIME_BY_TYPE[file_type]
    normalized_declared_type = (declared_content_type or "").split(";", 1)[0].strip()
    if normalized_declared_type != expected_content_type:
        raise MaterialUploadValidationError(
            "The declared file type does not match the selected format",
            "INVALID_FILE_TYPE",
        )

    size_bytes = source.stat().st_size
    if size_bytes <= 0 or size_bytes > max_size_bytes:
        raise MaterialUploadValidationError(
            "File size exceeds the allowed limit", "FILE_TOO_LARGE"
        )

    if file_type == "pdf":
        _validate_pdf_signature(source)
    else:
        _validate_ooxml_package(
            source,
            file_type=file_type,
            max_archive_uncompressed_bytes=(
                max_archive_uncompressed_bytes
                if max_archive_uncompressed_bytes is not None
                else min(
                    max_size_bytes * _MAX_ARCHIVE_COMPRESSION_RATIO,
                    _MAX_ARCHIVE_UNCOMPRESSED_BYTES,
                )
            ),
        )

    return ValidatedMaterialUpload(
        file_type=file_type,
        content_type=expected_content_type,
        size_bytes=size_bytes,
    )


def infer_material_file_type(filename: str) -> str:
    file_type = _TYPE_BY_EXTENSION.get(Path(filename).suffix.lower())
    if file_type is None:
        raise MaterialUploadValidationError(
            "Only PDF, DOCX, and PPTX materials are supported", "INVALID_FILE_TYPE"
        )
    return file_type


def _validate_pdf_signature(source: Path) -> None:
    with source.open("rb") as handle:
        signature = handle.read(5)
    if signature != b"%PDF-":
        raise MaterialUploadValidationError(
            "The file contents do not match a PDF document", "INVALID_FILE_SIGNATURE"
        )


def _validate_ooxml_package(
    source: Path, *, file_type: str, max_archive_uncompressed_bytes: int
) -> None:
    if not zipfile.is_zipfile(source):
        raise MaterialUploadValidationError(
            "The file contents do not match the selected Office format",
            "INVALID_FILE_SIGNATURE",
        )

    required_document = (
        "word/document.xml" if file_type == "docx" else "ppt/presentation.xml"
    )
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if len(infos) > _MAX_ARCHIVE_ENTRIES:
                _unsafe_archive()
            total_uncompressed = 0
            has_content_types = False
            has_required_document = False
            for info in infos:
                _validate_zip_info(info)
                total_uncompressed += info.file_size
                if total_uncompressed > max_archive_uncompressed_bytes:
                    _unsafe_archive()
                if info.filename == "[Content_Types].xml":
                    has_content_types = True
                if info.filename == required_document:
                    has_required_document = True
            if not has_content_types or not has_required_document:
                raise MaterialUploadValidationError(
                    "The file contents do not match the selected Office format",
                    "INVALID_FILE_SIGNATURE",
                )
    except zipfile.BadZipFile as exc:
        raise MaterialUploadValidationError(
            "The file contents do not match the selected Office format",
            "INVALID_FILE_SIGNATURE",
        ) from exc


def _validate_zip_info(info: zipfile.ZipInfo) -> None:
    posix_path = PurePosixPath(info.filename)
    windows_path = PureWindowsPath(info.filename)
    mode = info.external_attr >> 16
    is_symlink = stat.S_IFMT(mode) == stat.S_IFLNK
    compressed_size = max(info.compress_size, 1)
    compression_ratio = info.file_size / compressed_size
    if (
        info.flag_bits & 0x1
        or "\\" in info.filename
        or posix_path.is_absolute()
        or ".." in posix_path.parts
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in windows_path.parts
        or is_symlink
        or compression_ratio > _MAX_ARCHIVE_COMPRESSION_RATIO
    ):
        _unsafe_archive()


def _unsafe_archive() -> None:
    raise MaterialUploadValidationError(
        "The Office archive does not meet upload safety requirements", "UNSAFE_ARCHIVE"
    )
