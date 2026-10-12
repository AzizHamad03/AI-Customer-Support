from django.conf import settings
from langchain_openai import OpenAIEmbeddings
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)


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
        max_retries=1,
        chunk_size=32,
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
        return get_embedding_client().embed_documents(texts)
    except (APIConnectionError, APIStatusError) as exc:
        raise EmbeddingError(friendly_api_error(exc)) from exc


def embed_question(question):
    try:
        return get_embedding_client().embed_query(question)
    except (APIConnectionError, APIStatusError) as exc:
        raise EmbeddingError(friendly_api_error(exc)) from exc