import logging

from django.db import transaction

from support.models import KnowledgeDocument



logger = logging.getLogger(__name__)


def delete_uploaded_file(storage, name):
    try:
        storage.delete(name)
    except Exception:
        logger.exception("Could not remove deleted document file: %s", name)

def list_documents():
    return KnowledgeDocument.objects.select_related(
        "uploaded_by",
        "replaces",
    )


def create_document(*, title, category, file, uploaded_by):
    document = KnowledgeDocument(
        title=title,
        category=category,
        file=file,
        uploaded_by=uploaded_by,
    )
    document.full_clean()
    document.save()
    return document


@transaction.atomic
def create_replacement_document(*, document_id, file, uploaded_by):
    original = KnowledgeDocument.objects.select_for_update().get(
        pk=document_id
    )

    if original.status != KnowledgeDocument.Status.READY:
        raise ValueError(
            "Only successfully indexed documents can be replaced."
        )

    if original.replacement_versions.filter(
        status=KnowledgeDocument.Status.READY
    ).exists():
        raise ValueError(
            "This document has already been replaced. "
            "Upload a replacement for its latest version instead."
        )

    if not original.is_active:
        raise ValueError(
            "Activate this document before uploading a replacement."
        )

    if original.replacement_versions.filter(
        status__in=[
            KnowledgeDocument.Status.PENDING,
            KnowledgeDocument.Status.EXTRACTED,
        ]
    ).exists():
        raise ValueError(
            "A replacement is already waiting for processing. "
            "Finish processing that replacement first."
        )

    replacement = KnowledgeDocument(
        title=original.title,
        category=original.category,
        file=file,
        version=original.version + 1,
        replaces=original,
        is_active=False,
        uploaded_by=uploaded_by,
    )
    replacement.full_clean()
    replacement.save()

    # Keep the original available until replacement indexing succeeds.
    return replacement


@transaction.atomic
def set_document_active(document_id, active):
    document = KnowledgeDocument.objects.select_for_update().get(
        pk=document_id
    )

    if active:
        if document.status != KnowledgeDocument.Status.READY:
            raise ValueError(
                "Index the document successfully before activating it."
            )

        if document.replacement_versions.filter(
            status=KnowledgeDocument.Status.READY
        ).exists():
            raise ValueError(
                "This document has been replaced and cannot be "
                "reactivated. Activate its latest version instead."
            )

    document.is_active = active
    document.save(update_fields=["is_active"])

    return document

@transaction.atomic
def delete_document(document_id):
    original_id = KnowledgeDocument.objects.values_list(
        "replaces_id", flat=True
    ).get(pk=document_id)

    # Match the lock order used by replacement indexing.
    if original_id is not None:
        KnowledgeDocument.objects.select_for_update().get(
            pk=original_id
        )

    document = KnowledgeDocument.objects.select_for_update().get(
        pk=document_id
    )

    if document.replaces_id != original_id:
        raise ValueError(
            "The document relationship changed. Please reload and try again."
        )

    if document.replacement_versions.exists():
        raise ValueError(
            "This document has replacement versions. "
            "Delete those versions first, or deactivate this document."
        )

    title = document.title
    storage = document.file.storage
    file_name = document.file.name

    # Chunks are deleted; existing citation snapshots remain.
    document.delete()

    # Remove the uploaded file only after the database deletion commits.
    if file_name:
        transaction.on_commit(
            lambda: delete_uploaded_file(storage, file_name)
        )

    return title