from django.conf import settings
from pgvector.django import CosineDistance

from support.ai.embeddings import embed_question
from support.models import DocumentChunk, KnowledgeDocument


def search_knowledge_base(question, limit=5):
    eligible_chunks = DocumentChunk.objects.filter(
        document__is_active=True,
        document__status=KnowledgeDocument.Status.READY,
        embedding__isnull=False,
    )

    if not eligible_chunks.exists():
        return []

    query_vector = embed_question(question)

    matches = (
        eligible_chunks
        .select_related("document")
        .annotate(
            distance=CosineDistance("embedding", query_vector)
        )
        .filter(
            distance__lte=settings.RETRIEVAL_MAX_DISTANCE
        )
        .order_by("distance", "pk")[:limit]
    )

    return [
        {
            "chunk_id": chunk.pk,
            "title": chunk.document.title,
            "document_version": chunk.document.version,
            "page_number": chunk.page_number,
            "text": chunk.text,
            "distance": float(chunk.distance),
            "is_txt": chunk.document.file.name.lower().endswith(".txt"),
        }
        for chunk in matches
    ]