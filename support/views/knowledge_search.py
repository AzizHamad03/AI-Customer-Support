from django.shortcuts import render

from support.ai.embeddings import EmbeddingError
from support.demo_access import is_demo_user, workspace_required
from support.forms import KnowledgeSearchForm
from support.services.demo_quotas import (
    DemoActionQuotaExceeded,
    consume_demo_search_quota,
)
from support.services.retrieval import search_knowledge_base


@workspace_required
def knowledge_search(request):
    form = KnowledgeSearchForm(
        request.POST if request.method == "POST" else None,
    )
    results = []
    searched = False
    quota_error = None

    if request.method == "POST" and form.is_valid():
        try:
            consume_demo_search_quota(request.user)
            results = search_knowledge_base(
                form.cleaned_data["question"],
                demo_user_id=request.user.pk if is_demo_user(request.user) else None,
            )
        except DemoActionQuotaExceeded as exc:
            quota_error = exc
            form.add_error(None, str(exc))
        except EmbeddingError as exc:
            form.add_error(None, str(exc))
        else:
            searched = True

    response = render(
        request,
        "support/knowledge_search.html",
        {
            "form": form,
            "results": results,
            "searched": searched,
        },
        status=429 if quota_error else 200,
    )

    if quota_error:
        response["Retry-After"] = str(quota_error.retry_after)

    return response