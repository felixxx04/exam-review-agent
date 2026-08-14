from __future__ import annotations

import stat
import zipfile

import pytest

from app.services import material_upload_validation as upload_validation
from app.services.material_upload_validation import (
    MaterialUploadValidationError,
    validate_material_upload,
)


MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _write_ooxml(path, *, office_directory: str) -> None:
    main_document = {
        "word": "document.xml",
        "ppt": "presentation.xml",
    }[office_directory]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(f"{office_directory}/{main_document}", "<document />")


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


def test_accepts_a_well_formed_pptx_package(tmp_path) -> None:
    source = tmp_path / "slides.pptx"
    _write_ooxml(source, office_directory="ppt")

    validated = validate_material_upload(
        source,
        filename="slides.pptx",
        declared_content_type=PPTX_MIME,
        max_size_bytes=1_000,
    )

    assert validated.file_type == "pptx"
    assert validated.content_type == PPTX_MIME


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


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "/absolute.xml",
        "word/../../escape.xml",
        "C:/escape.xml",
    ],
)
def test_rejects_ooxml_archive_absolute_and_parent_paths(tmp_path, unsafe_name) -> None:
    source = tmp_path / "unsafe-path.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")
        archive.writestr(unsafe_name, "escape")

    with pytest.raises(MaterialUploadValidationError) as error:
        validate_material_upload(
            source,
            filename="unsafe-path.docx",
            declared_content_type=DOCX_MIME,
            max_size_bytes=2_000,
        )

    assert error.value.code == "UNSAFE_ARCHIVE"


@pytest.mark.parametrize(
    "unsafe_name",
    [r"..\escape.xml", r"word\..\..\escape.xml"],
)
def test_rejects_raw_windows_archive_parent_paths(unsafe_name) -> None:
    archive_entry = zipfile.ZipInfo("placeholder.xml")
    archive_entry.filename = unsafe_name

    with pytest.raises(MaterialUploadValidationError) as error:
        upload_validation._validate_zip_info(archive_entry)

    assert error.value.code == "UNSAFE_ARCHIVE"


def test_rejects_ooxml_archive_symlink_entry(tmp_path) -> None:
    source = tmp_path / "symlink.docx"
    symlink = zipfile.ZipInfo("word/link.xml")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")
        archive.writestr(symlink, "document.xml")

    with pytest.raises(MaterialUploadValidationError) as error:
        validate_material_upload(
            source,
            filename="symlink.docx",
            declared_content_type=DOCX_MIME,
            max_size_bytes=2_000,
        )

    assert error.value.code == "UNSAFE_ARCHIVE"


def test_rejects_encrypted_ooxml_entry_metadata() -> None:
    encrypted = zipfile.ZipInfo("word/document.xml")
    encrypted.flag_bits |= 0x1

    with pytest.raises(MaterialUploadValidationError) as error:
        upload_validation._validate_zip_info(encrypted)

    assert error.value.code == "UNSAFE_ARCHIVE"


def test_rejects_ooxml_archive_with_too_many_entries(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(upload_validation, "_MAX_ARCHIVE_ENTRIES", 2)
    source = tmp_path / "too-many-entries.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")
        archive.writestr("word/styles.xml", "<styles />")

    with pytest.raises(MaterialUploadValidationError) as error:
        validate_material_upload(
            source,
            filename="too-many-entries.docx",
            declared_content_type=DOCX_MIME,
            max_size_bytes=2_000,
        )

    assert error.value.code == "UNSAFE_ARCHIVE"


def test_rejects_ooxml_archive_excessive_compression_ratio(tmp_path) -> None:
    source = tmp_path / "compression-bomb.pptx"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("ppt/document.xml", "x" * 20_000)

    with pytest.raises(MaterialUploadValidationError) as error:
        validate_material_upload(
            source,
            filename="compression-bomb.pptx",
            declared_content_type=PPTX_MIME,
            max_size_bytes=10_000,
            max_archive_uncompressed_bytes=100_000,
        )

    assert error.value.code == "UNSAFE_ARCHIVE"


def test_rejects_ooxml_package_that_does_not_match_selected_format(tmp_path) -> None:
    source = tmp_path / "forged.pptx"
    _write_ooxml(source, office_directory="word")

    with pytest.raises(MaterialUploadValidationError) as error:
        validate_material_upload(
            source,
            filename="forged.pptx",
            declared_content_type=PPTX_MIME,
            max_size_bytes=1_000,
        )

    assert error.value.code == "INVALID_FILE_SIGNATURE"


def test_rejects_ooxml_package_without_required_main_document(tmp_path) -> None:
    source = tmp_path / "missing-document.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/media/image.png", b"not a document")

    with pytest.raises(MaterialUploadValidationError) as error:
        validate_material_upload(
            source,
            filename="missing-document.docx",
            declared_content_type=DOCX_MIME,
            max_size_bytes=1_000,
        )

    assert error.value.code == "INVALID_FILE_SIGNATURE"


def test_rejects_ooxml_archive_that_exceeds_safe_uncompressed_size(tmp_path) -> None:
    source = tmp_path / "oversized.pptx"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("ppt/presentation.xml", "x" * 10_000)

    with pytest.raises(MaterialUploadValidationError) as error:
        validate_material_upload(
            source,
            filename="oversized.pptx",
            declared_content_type=PPTX_MIME,
            max_size_bytes=20_000,
            max_archive_uncompressed_bytes=1_000,
        )

    assert error.value.code == "UNSAFE_ARCHIVE"
