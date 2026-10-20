import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import (
    require_http_methods,
    require_POST,
)

from support.forms import DocumentReplacementForm, DocumentUploadForm
from support.models import DocumentProcessingJob, KnowledgeDocument
from support.services.documents import (
    create_document,
    create_replacement_document,
    delete_document,
    list_documents,
    set_document_active,
)
from support.services.processing_jobs import queue_document_processing




logger = logging.getLogger(__name__)

@staff_member_required(login_url="support:login")
def document_list(request):
    return render(
        request,
        "support/document_list.html",
        {"documents": list_documents()},
    )


@staff_member_required(login_url="support:login")
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


@staff_member_required(login_url="support:login")
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


@staff_member_required(login_url="support:login")
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

    processing_job = DocumentProcessingJob.objects.filter(
        document=document,
    ).first()

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
            "processing_job": processing_job,
            "processing_busy": bool(
                processing_job and processing_job.is_busy
            ),
        },
    )


@staff_member_required(login_url="support:login")
@require_POST
def document_process(request, pk):
    document = get_object_or_404(KnowledgeDocument, pk=pk)

    try:
        job, queued = queue_document_processing(document.pk)

    except KnowledgeDocument.DoesNotExist:
        messages.info(
            request,
            "This document is no longer available.",
        )
        return redirect("support:document_list")

    except DatabaseError:
        logger.exception("Could not queue document processing")
        messages.error(
            request,
            "Processing could not be queued. Please try again.",
        )

    else:
        if job is None:
            messages.info(
                request,
                "This document is already indexed.",
            )
        elif queued:
            messages.success(
                request,
                "Document processing queued. "
                "You can leave this page while it runs.",
            )
        else:
            messages.info(
                request,
                "This document is already queued or processing.",
            )

    return redirect(
        "support:document_detail",
        pk=document.pk,
    )


@staff_member_required(login_url="support:login")
@require_POST
def document_prepare_chunks(request, pk):
    return document_process(request, pk)


@staff_member_required(login_url="support:login")
@require_POST
def document_index(request, pk):
    return document_process(request, pk)


@staff_member_required(login_url="support:login")
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

@staff_member_required(login_url="support:login")
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