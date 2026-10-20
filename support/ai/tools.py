from pydantic import BaseModel, ConfigDict, Field

from support.services.retrieval import (
    search_knowledge_base as retrieve_knowledge_base,
)


class SearchArguments(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    query: str = Field(
        min_length=1,
        max_length=1000,
    )


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search active store documents for evidence. "
                "Use before answering policy or product questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]


def execute_tool(name, arguments):
    if name != "search_knowledge_base":
        raise ValueError("Unknown tool.")

    parsed = SearchArguments.model_validate(arguments)
    query = parsed.query.strip()

    if not query:
        raise ValueError("Enter a non-empty search query.")

    return {
        "matches": retrieve_knowledge_base(query),
    }