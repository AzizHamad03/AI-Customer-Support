from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from support.ai.embeddings import EmbeddingError
from support.forms import KnowledgeSearchForm
from support.services.retrieval import search_knowledge_base


@staff_member_required
def knowledge_search(request):
    form = KnowledgeSearchForm(
        request.POST if request.method == "POST" else None
    )
    results = []
    searched = False

    if request.method == "POST" and form.is_valid():
        try:
            results = search_knowledge_base(
                form.cleaned_data["question"]
            )
        except EmbeddingError as exc:
            form.add_error(None, str(exc))
        else:
            searched = True

    return render(
        request,
        "support/knowledge_search.html",
        {
            "form": form,
            "results": results,
            "searched": searched,
        },
    )