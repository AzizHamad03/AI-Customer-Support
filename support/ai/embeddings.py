from django.conf import settings
from langchain_openai import OpenAIEmbeddings
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)
from tiktoken import encoding_for_model

from support.services.demo_quotas import consume_openai_request_quota

EMBEDDING_BATCH_SIZE = 32
DEMO_MAX_EMBEDDING_TOKENS = 8000

class EmbeddingError(Exception):
    pass


def get_embedding_client():
    if not settings.OPENAI_API_KEY:
        raise EmbeddingError(
            "Set OPENAI_API_KEY in .env and restart the server."
        )

    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        dimensions=1536,
        api_key=settings.OPENAI_API_KEY,
        timeout=30,
        max_retries=0 if settings.DEMO_OPENAI_DAILY_LIMIT else 1,
        chunk_size=EMBEDDING_BATCH_SIZE,
        check_embedding_ctx_length=not settings.DEMO_OPENAI_DAILY_LIMIT,
    )


def friendly_api_error(error):
    if isinstance(error, AuthenticationError):
        return "The API key was rejected. Check OPENAI_API_KEY."

    if isinstance(error, RateLimitError):
        return (
            "The API quota or rate limit was reached. "
            "Check your API billing and limits, then try again."
        )

    if isinstance(error, (APIConnectionError, APITimeoutError)):
        return "The embedding service could not be reached. Try again."

    return "The embedding request failed. Try again."


def embed_document_texts(texts):
    try:
        client = get_embedding_client()

        if not settings.DEMO_OPENAI_DAILY_LIMIT:
            return client.embed_documents(texts)

        encoding = encoding_for_model(settings.EMBEDDING_MODEL)
        for text in texts:
            if len(encoding.encode_ordinary(text)) > DEMO_MAX_EMBEDDING_TOKENS:
                raise EmbeddingError(
                    "A section of this document is too long for the demo. "
                    "Upload a shorter document."
                )

        vectors = []
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[start:start + EMBEDDING_BATCH_SIZE]
            consume_openai_request_quota()
            vectors.extend(client.embed_documents(batch))

        return vectors

    except (APIConnectionError, APIStatusError) as exc:
        raise EmbeddingError(friendly_api_error(exc)) from exc


def embed_question(question):
    try:
        client = get_embedding_client()
        consume_openai_request_quota()
        return client.embed_query(question)
    except (APIConnectionError, APIStatusError) as exc:
        raise EmbeddingError(friendly_api_error(exc)) from exc