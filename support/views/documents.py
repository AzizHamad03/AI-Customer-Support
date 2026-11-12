import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import (
    require_http_methods,
    require_POST,
)

from support.demo_access import is_demo_user, workspace_documents, workspace_required
from support.services.demo_quotas import (
    DEMO_UPLOAD_MAX_BYTES,
    DemoUploadQuotaExceeded,
    reserve_demo_upload,
    DemoActionQuotaExceeded,
)
from support.forms import DocumentReplacementForm, DocumentUploadForm
from support.models import DocumentProcessingJob, KnowledgeDocument
from support.services.documents import (
    create_document,
    create_replacement_document,
    delete_document,
    set_document_active,
)
from support.services.processing_jobs import queue_document_processing


logger = logging.getLogger(__name__)


@workspace_required
def document_list(request):
    return render(
        request,
        "support/document_list.html",
        {
            "documents": workspace_documents(request.user).select_related(
                "uploaded_by", "replaces"
            )
        },
    )


def _valid_upload(form, user):
    if not form.is_valid():
        return False

    if is_demo_user(user) and form.cleaned_data["file"].size > DEMO_UPLOAD_MAX_BYTES:
        form.add_error("file", "Demo files must be 2 MiB or smaller.")
        return False

    return True


def _upload_response(request, template, context, quota_error=None):
    if quota_error is None:
        return render(request, template, context)

    context["form"].add_error(None, str(quota_error))
    response = render(request, template, context, status=429)
    response["Retry-After"] = str(quota_error.retry_after)
    return response


@workspace_required
def document_upload(request):
    form = DocumentUploadForm()
    quota_error = None

    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)

        if _valid_upload(form, request.user):
            try:
                with reserve_demo_upload(request.user):
                    document = create_document(
                        title=form.cleaned_data["title"],
                        category=form.cleaned_data["category"],
                        file=form.cleaned_data["file"],
                        uploaded_by=request.user,
                    )
            except DemoUploadQuotaExceeded as exc:
                quota_error = exc
            else:
                messages.success(
                    request,
                    "Document uploaded. Click Process document to prepare it for chat.",
                )
                return redirect("support:document_detail", pk=document.pk)

    if is_demo_user(request.user):
        form.fields["file"].help_text = (
            "Upload a text-based PDF or UTF-8 TXT file, up to 2 MiB."
        )

    return _upload_response(
        request,
        "support/document_upload.html",
        {"form": form},
        quota_error,
    )


@workspace_required
def document_replace(request, pk):
    original = get_object_or_404(workspace_documents(request.user), pk=pk)
    form = DocumentReplacementForm()
    quota_error = None

    if request.method == "POST":
        form = DocumentReplacementForm(request.POST, request.FILES)

        if _valid_upload(form, request.user):
            try:
                with reserve_demo_upload(request.user):
                    replacement = create_replacement_document(
                        document_id=original.pk,
                        file=form.cleaned_data["file"],
                        uploaded_by=request.user,
                    )
            except DemoUploadQuotaExceeded as exc:
                quota_error = exc
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

    if is_demo_user(request.user):
        form.fields["file"].help_text = (
            "Upload a text-based PDF or UTF-8 TXT file, up to 2 MiB."
        )

    return _upload_response(
        request,
        "support/document_replace.html",
        {
            "form": form,
            "document": original,
            "next_version": original.version + 1,
        },
        quota_error,
    )


@workspace_required
def document_detail(request, pk):
    document = get_object_or_404(
        workspace_documents(request.user).select_related("replaces"),
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


@workspace_required
@require_POST
def document_process(request, pk):
    document = get_object_or_404(workspace_documents(request.user), pk=pk)

    try:
        job, queued = queue_document_processing(document.pk)

    except KnowledgeDocument.DoesNotExist:
        messages.info(
            request,
            "This document is no longer available.",
        )
        return redirect("support:document_list")

    except DemoActionQuotaExceeded as exc:
        messages.error(request, str(exc))

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


@workspace_required
@require_POST
def document_prepare_chunks(request, pk):
    return document_process(request, pk)


@workspace_required
@require_POST
def document_index(request, pk):
    return document_process(request, pk)


@workspace_required
@require_POST
def document_set_active(request, pk):
    document = get_object_or_404(workspace_documents(request.user), pk=pk)
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

    return redirect(
        "support:document_detail",
        pk=document.pk,
    )


@workspace_required
@require_http_methods(["GET", "POST"])
def document_delete(request, pk):
    document = get_object_or_404(workspace_documents(request.user), pk=pk)

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