import logging
from pathlib import Path

from pypdf import PdfReader

from support.models import KnowledgeDocument

logger = logging.getLogger(__name__)

MAX_PAGES = 100
MAX_CHARACTERS = 200_000


class DocumentProcessingError(Exception):
    pass


def clean_text(text):
    # PostgreSQL text fields cannot store null characters.
    return text.replace("\x00", "").strip()


def extract_pages(document):
    extension = Path(document.file.name).suffix.lower()

    with document.file.open("rb") as source:
        if extension == ".txt":
            try:
                text = source.read().decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise DocumentProcessingError(
                    "This TXT file is not UTF-8 encoded. "
                    "Save it as UTF-8 and upload it again."
                ) from exc

            pages = [{"page": 1, "text": clean_text(text)}]

        elif extension == ".pdf":
            reader = PdfReader(source)

            if reader.is_encrypted:
                raise DocumentProcessingError(
                    "Password-protected PDFs are not supported."
                )

            if len(reader.pages) > MAX_PAGES:
                raise DocumentProcessingError(
                    f"Upload a PDF with no more than {MAX_PAGES} pages."
                )

            pages = []
            character_count = 0

            for number, page in enumerate(reader.pages, start=1):
                text = clean_text(page.extract_text() or "")
                character_count += len(text)

                if character_count > MAX_CHARACTERS:
                    raise DocumentProcessingError(
                        "This document contains too much text. "
                        "Upload a smaller document."
                    )

                if text:
                    pages.append({"page": number, "text": text})

        else:
            raise DocumentProcessingError(
                "Only PDF and TXT files are supported."
            )

    pages = [page for page in pages if page["text"]]

    if not pages:
        raise DocumentProcessingError(
            "No readable text was found. Upload a non-empty TXT file "
            "or a text-based PDF. Scanned PDFs are not supported."
        )

    if sum(len(page["text"]) for page in pages) > MAX_CHARACTERS:
        raise DocumentProcessingError(
            "This document contains too much text. "
            "Upload a smaller document."
        )

    return pages


def process_document(document):
    # Indexed documents will need a separate replacement/reindex workflow.
    if document.status == KnowledgeDocument.Status.READY:
        raise DocumentProcessingError(
            "This document is already indexed."
        )

    document.extracted_pages = []
    document.processing_error = ""

    try:
        document.extracted_pages = extract_pages(document)
        document.status = KnowledgeDocument.Status.EXTRACTED
    except DocumentProcessingError as exc:
        document.status = KnowledgeDocument.Status.FAILED
        document.processing_error = str(exc)
    except Exception:
        logger.exception(
            "Document extraction failed for document %s",
            document.pk,
        )
        document.status = KnowledgeDocument.Status.FAILED
        document.processing_error = (
            "The document could not be read. "
            "Check that the file is valid and try again."
        )

    document.save(
        update_fields=[
            "extracted_pages",
            "processing_error",
            "status",
        ]
    )

    return document