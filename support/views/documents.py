from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from support.ai.embeddings import EmbeddingError
from support.forms import DocumentReplacementForm, DocumentUploadForm
from support.models import KnowledgeDocument
from support.services.chunking import prepare_document_chunks
from support.services.document_processing import (
    DocumentProcessingError,
    
)
from support.services.documents import (
    create_document,
    create_replacement_document,
    list_documents,
    set_document_active,
    delete_document,
)
from support.services.indexing import index_document
from support.services.document_pipeline import (
    process_and_index_document,
)

import logging

from django.db import DatabaseError
from django.db.models.deletion import ProtectedError
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

@staff_member_required
def document_list(request):
    return render(
        request,
        "support/document_list.html",
        {"documents": list_documents()},
    )


@staff_member_required
def document_upload(request):
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)

        if form.is_valid():
            document = create_document(
                title=form.cleaned_data["title"],
                category=form.cleaned_data["category"],
                file=form.cleaned_data["file"],
                uploaded_by=request.user,
            )
            messages.success(
                request,
                "Document uploaded. Click Process document to prepare it for chat.",
            )
            return redirect(
                "support:document_detail",
                pk=document.pk,
            )
    else:
        form = DocumentUploadForm()

    return render(
        request,
        "support/document_upload.html",
        {"form": form},
    )


@staff_member_required
def document_replace(request, pk):
    original = get_object_or_404(KnowledgeDocument, pk=pk)

    if request.method == "POST":
        form = DocumentReplacementForm(request.POST, request.FILES)

        if form.is_valid():
            try:
                replacement = create_replacement_document(
                    document_id=original.pk,
                    file=form.cleaned_data["file"],
                    uploaded_by=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(
                    request,
                    f"Version {replacement.version} uploaded. "
                    "Click Process document to prepare it for chat. "
                    "The original remains available "
                    "until replacement indexing succeeds.",
                )
                return redirect(
                    "support:document_detail",
                    pk=replacement.pk,
                )
    else:
        form = DocumentReplacementForm()

    return render(
        request,
        "support/document_replace.html",
        {
            "document": original,
            "next_version": original.version + 1,
            "form": form,
        },
    )


@staff_member_required
def document_detail(request, pk):
    document = get_object_or_404(
        KnowledgeDocument.objects.select_related("replaces"),
        pk=pk,
    )

    character_count = sum(
        len(page["text"])
        for page in document.extracted_pages
    )

    replacement = document.replacement_versions.filter(
        status=KnowledgeDocument.Status.READY
    ).first()

    pending_replacement = document.replacement_versions.filter(
        status__in=[
            KnowledgeDocument.Status.PENDING,
            KnowledgeDocument.Status.EXTRACTED,
        ]
    ).first()

    can_replace = (
        document.status == KnowledgeDocument.Status.READY
        and document.is_active
        and replacement is None
        and pending_replacement is None
    )

    return render(
        request,
        "support/document_detail.html",
        {
            "document": document,
            "character_count": character_count,
            "chunks": list(document.chunks.all()),
            "replacement": replacement,
            "pending_replacement": pending_replacement,
            "can_replace": can_replace,
        },
    )


@staff_member_required
@require_POST
def document_process(request, pk):
    document = get_object_or_404(KnowledgeDocument, pk=pk)

    try:
        process_and_index_document(document.pk)

    except (
        DocumentProcessingError,
        EmbeddingError,
        ValueError,
    ) as exc:
        messages.error(request, str(exc))

    else:
        messages.success(
            request,
            "Document processing completed. "
            "Review its availability below.",
        )

    return redirect(
        "support:document_detail",
        pk=document.pk,
    )


@staff_member_required
@require_POST
def document_prepare_chunks(request, pk):
    document = get_object_or_404(KnowledgeDocument, pk=pk)

    try:
        count = prepare_document_chunks(document.pk)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Prepared {count} chunk(s).",
        )

    return redirect("support:document_detail", pk=document.pk)


@staff_member_required
@require_POST
def document_index(request, pk):
    document = get_object_or_404(KnowledgeDocument, pk=pk)

    try:
        count = index_document(document.pk)
    except EmbeddingError as exc:
        document.processing_error = str(exc)
        document.save(update_fields=["processing_error"])
        messages.error(request, str(exc))
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        if document.replaces_id:
            messages.success(
                request,
                f"Indexed {count} chunk(s). "
                f"Version {document.version} is now active, "
                "and the original version has been deactivated.",
            )
        else:
            messages.success(
                request,
                f"Indexed {count} chunk(s). The document is ready.",
            )

    return redirect("support:document_detail", pk=document.pk)


@staff_member_required
@require_POST
def document_set_active(request, pk):
    document = get_object_or_404(KnowledgeDocument, pk=pk)
    action = request.POST.get("action")

    if action not in {"activate", "deactivate"}:
        messages.error(request, "Invalid document action.")
        return redirect("support:document_detail", pk=pk)

    try:
        set_document_active(
            document.pk,
            active=action == "activate",
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            "Document activated."
            if action == "activate"
            else "Document deactivated.",
        )

    return redirect("support:document_detail", pk=pk)

@staff_member_required
@require_http_methods(["GET", "POST"])
def document_delete(request, pk):
    document = get_object_or_404(KnowledgeDocument, pk=pk)

    context = {
        "document": document,
        "replacement_versions": document.replacement_versions.order_by(
            "version", "pk"
        ),
    }

    if request.method == "POST":
        if request.POST.get("confirm") != "yes":
            messages.error(request, "Confirm deletion before continuing.")
            return redirect("support:document_delete", pk=pk)

        try:
            title = delete_document(document.pk)
        except KnowledgeDocument.DoesNotExist:
            messages.info(request, "This document has already been deleted.")
            return redirect("support:document_list")
        except ProtectedError:
            messages.error(
                request,
                "This document has replacement versions. "
                "Delete those versions first, or deactivate it.",
            )
            return redirect("support:document_delete", pk=pk)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("support:document_delete", pk=pk)
        except DatabaseError:
            logger.exception("Document deletion failed")
            messages.error(
                request,
                "The document could not be deleted. Please try again.",
            )
            return render(
                request,
                "support/document_delete.html",
                context,
                status=503,
            )

        messages.success(
            request,
            f'Document "{title}" deleted. '
            "Previous messages and citation text have been preserved.",
        )
        return redirect("support:document_list")

    return render(
        request,
        "support/document_delete.html",
        context,
    )