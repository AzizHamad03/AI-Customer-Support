from django.db import transaction

from support.models import KnowledgeDocument


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