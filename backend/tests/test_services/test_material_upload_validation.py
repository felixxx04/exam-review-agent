from __future__ import annotations

import zipfile

import pytest

from app.services.material_upload_validation import (
    MaterialUploadValidationError,
    validate_material_upload,
)


MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _write_ooxml(path, *, office_directory: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(f"{office_directory}/document.xml", "<document />")


def test_accepts_a_pdf_when_extension_mime_and_magic_bytes_agree(tmp_path) -> None:
    source = tmp_path / "notes.pdf"
    source.write_bytes(MINIMAL_PDF)

    validated = validate_material_upload(
        source,
        filename="notes.pdf",
        declared_content_type="application/pdf",
        max_size_bytes=1_000,
    )

    assert validated.file_type == "pdf"
    assert validated.content_type == "application/pdf"
    assert validated.size_bytes == len(MINIMAL_PDF)


def test_rejects_a_pdf_name_when_real_magic_bytes_are_not_pdf(tmp_path) -> None:
    source = tmp_path / "forged.pdf"
    source.write_bytes(b"not a PDF document")

    with pytest.raises(MaterialUploadValidationError) as error:
        validate_material_upload(
            source,
            filename="forged.pdf",
            declared_content_type="application/pdf",
            max_size_bytes=1_000,
        )

    assert error.value.code == "INVALID_FILE_SIGNATURE"


def test_rejects_declared_mime_type_that_conflicts_with_extension(tmp_path) -> None:
    source = tmp_path / "notes.pdf"
    source.write_bytes(MINIMAL_PDF)

    with pytest.raises(MaterialUploadValidationError) as error:
        validate_material_upload(
            source,
            filename="notes.pdf",
            declared_content_type=DOCX_MIME,
            max_size_bytes=1_000,
        )

    assert error.value.code == "INVALID_FILE_TYPE"


def test_accepts_a_well_formed_docx_package(tmp_path) -> None:
    source = tmp_path / "notes.docx"
    _write_ooxml(source, office_directory="word")

    validated = validate_material_upload(
        source,
        filename="notes.docx",
        declared_content_type=DOCX_MIME,
        max_size_bytes=1_000,
    )

    assert validated.file_type == "docx"
    assert validated.content_type == DOCX_MIME


def test_rejects_ooxml_archive_path_traversal(tmp_path) -> None:
    source = tmp_path / "forged.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")
        archive.writestr("../escape.txt", "escape")

    with pytest.raises(MaterialUploadValidationError) as error:
        validate_material_upload(
            source,
            filename="forged.docx",
            declared_content_type=DOCX_MIME,
            max_size_bytes=1_000,
        )

    assert error.value.code == "UNSAFE_ARCHIVE"


def test_rejects_ooxml_archive_that_exceeds_safe_uncompressed_size(tmp_path) -> None:
    source = tmp_path / "oversized.pptx"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("ppt/document.xml", "x" * 10_000)

    with pytest.raises(MaterialUploadValidationError) as error:
        validate_material_upload(
            source,
            filename="oversized.pptx",
            declared_content_type=PPTX_MIME,
            max_size_bytes=20_000,
            max_archive_uncompressed_bytes=1_000,
        )

    assert error.value.code == "UNSAFE_ARCHIVE"
