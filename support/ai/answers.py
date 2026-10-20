import json

from django.conf import settings
from langchain_core.exceptions import OutputParserException
from langchain_openai import ChatOpenAI
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)
from pydantic import BaseModel, Field, ValidationError
from support.ai.prompt_loader import load_prompt

class ChatError(Exception):
    pass


class StandaloneQuestion(BaseModel):
    question: str = Field(
        description="The current customer question rewritten with context."
    )


class GroundedAnswer(BaseModel):
    supported: bool = Field(
        description="Whether the passages support answering the question."
    )
    needs_human_support: bool = Field(
        description=(
            "True when the customer requests human help or reports an "
            "issue requiring staff action, such as a damaged delivery, "
            "a missing order, or a refund or replacement request."
        )
    )
    answer: str = Field(description="A concise customer-facing answer.")
    source_keys: list[str] = Field(
        description="Identifiers of passages supporting the answer."
    )


def get_chat_model():
    if not settings.OPENAI_API_KEY:
        raise ChatError("Set OPENAI_API_KEY and restart the server.")

    return ChatOpenAI(
        model=settings.CHAT_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
        timeout=30,
        max_retries=1,
    )


def invoke_structured(schema, system_prompt, payload):
    try:
        model = get_chat_model().with_structured_output(
            schema,
            method="json_schema",
        )

        result = model.invoke(
            [
                ("system", system_prompt),
                ("human", json.dumps(payload, ensure_ascii=False)),
            ]
        )

        if result is None:
            raise ChatError("The AI service did not return a usable response.")

        return result

    except AuthenticationError as exc:
        raise ChatError("The API key was rejected.") from exc
    except RateLimitError as exc:
        raise ChatError(
            "The API quota or rate limit was reached. "
            "Check your API billing and limits."
        ) from exc
    except (APIConnectionError, APIStatusError) as exc:
        raise ChatError(
            "The AI service is unavailable. Please try again."
        ) from exc
    except (OutputParserException, ValidationError) as exc:
        raise ChatError(
            "The AI response could not be read. Please try again."
        ) from exc


def make_standalone_question(question, history):
    if not history:
        return question

    result = invoke_structured(
        StandaloneQuestion,
        load_prompt("rewrite_question"),
        {
            "history": history,
            "latest_question": question,
        },
    )

    rewritten = result.question.strip()

    if not rewritten or len(rewritten) > 1000:
        raise ChatError(
            "The follow-up question could not be interpreted."
        )

    return rewritten

def generate_answer(question, history, passages):
    return invoke_structured(
        GroundedAnswer,
        load_prompt("grounded_answer"),
        {
            "question": question,
            "history": history,
            "passages": passages,
        },
    )