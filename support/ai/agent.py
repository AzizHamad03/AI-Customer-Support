import json

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from openai import APIConnectionError, APIStatusError
from pydantic import ValidationError

from support.ai.answers import ChatError, get_chat_model
from support.ai.tools import TOOL_SCHEMAS, execute_tool
from support.ai.prompt_loader import load_prompt

MAX_MODEL_TURNS = 3
MAX_TOOL_CALLS = 2



def search_with_agent(question):
    model = get_chat_model().bind_tools(
        TOOL_SCHEMAS,
        strict=True,
        parallel_tool_calls=False,
    )

    messages = [
        SystemMessage(
            content=load_prompt("tool_selection")
        ),
        HumanMessage(
            content=json.dumps({"question": question})
        ),
    ]

    evidence = {}
    tool_calls = 0
    used_ids = set()

    for _ in range(MAX_MODEL_TURNS):
        try:
            response = model.invoke(messages)
        except (
            APIConnectionError,
            APIStatusError,
            ValidationError,
        ) as exc:
            raise ChatError(
                "The assistant tool service is unavailable. "
                "Please try again."
            ) from exc

        if not isinstance(response, AIMessage):
            raise ChatError(
                "The assistant did not return a usable tool response."
            )

        if response.invalid_tool_calls:
            raise ChatError(
                "The assistant returned an invalid tool request."
            )

        calls = response.tool_calls

        if not calls:
            return list(evidence.values())

        if len(calls) != 1:
            raise ChatError(
                "The assistant must request one tool at a time."
            )

        if tool_calls >= MAX_TOOL_CALLS:
            raise ChatError(
                "The assistant reached its tool limit. "
                "Please try again."
            )

        call = calls[0]
        call_id = call.get("id")

        if not call_id or call_id in used_ids:
            raise ChatError(
                "The assistant returned an invalid tool identifier."
            )

        used_ids.add(call_id)
        tool_calls += 1
        messages.append(response)

        try:
            result = execute_tool(
                call["name"],
                call["args"],
            )
        except (ValidationError, ValueError):
            result = {
                "error": (
                    "Invalid tool name or arguments. "
                    "Use an allowed tool."
                ),
            }
        else:
            for match in result.get("matches", []):
                evidence[match["chunk_id"]] = match

        messages.append(
            ToolMessage(
                content=json.dumps(result),
                tool_call_id=call_id,
            )
        )

    raise ChatError(
        "The assistant reached its tool limit. "
        "Please try again."
    )