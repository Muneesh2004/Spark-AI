import json

from langchain_core.messages import AIMessageChunk


def _content_to_text(content):
    """
    Convert LangChain message content into plain text.
    """

    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):

        parts = []

        for item in content:

            if isinstance(
                item,
                str
            ):

                parts.append(item)

                continue

            if isinstance(
                item,
                dict
            ):

                if item.get("type") == "text":

                    text = item.get(
                        "text",
                        ""
                    )

                    if text:
                        parts.append(text)

        return "".join(parts)

    return str(content)


def _tool_name_from_message(message):
    """
    Try to extract the tool name from a LangChain message.
    """

    if message is None:
        return None

    tool_calls = getattr(
        message,
        "tool_calls",
        None
    )

    if tool_calls:

        first = tool_calls[0]

        if isinstance(
            first,
            dict
        ):

            return first.get("name")

    return getattr(
        message,
        "name",
        None
    )


def stream_agent(
    agent,
    messages,
):
    """
    Stream a LangChain agent.

    Yields dictionaries.

    Examples:

        {
            "type": "token",
            "text": "hello"
        }

        {
            "type": "tool",
            "tool": "google_search",
            "status": "started"
        }

        {
            "type": "tool",
            "tool": "google_search",
            "status": "completed"
        }

    This function uses LangChain's v2 streaming format.
    """

    # Keep track of tool calls so that the frontend can
    # display useful status information.
    active_tools = {}

    for chunk in agent.stream(
        {
            "messages": messages
        },
        stream_mode=[
            "messages",
            "updates"
        ],
        version="v2",
    ):

        chunk_type = chunk.get(
            "type"
        )

        # ==================================================
        # TOKEN STREAM
        # ==================================================

        if chunk_type == "messages":

            token, metadata = chunk["data"]

            # AIMessageChunk contains generated content.
            if isinstance(
                token,
                AIMessageChunk
            ):

                text = _content_to_text(
                    token.content
                )

                if text:

                    yield {
                        "type": "token",
                        "text": text,
                    }

        # ==================================================
        # AGENT UPDATES
        # ==================================================

        elif chunk_type == "updates":

            data = chunk.get(
                "data",
                {}
            )

            # ----------------------------------------------
            # TOOL NODE
            # ----------------------------------------------

            if "tools" in data:

                tool_update = data[
                    "tools"
                ]

                if not tool_update:
                    continue

                messages_update = (
                    tool_update.get(
                        "messages",
                        []
                    )
                )

                if not messages_update:
                    continue

                tool_message = (
                    messages_update[-1]
                )

                tool_name = (
                    _tool_name_from_message(
                        tool_message
                    )
                    or "tool"
                )

                active_tools.pop(
                    tool_name,
                    None
                )

                yield {
                    "type": "tool",
                    "tool": tool_name,
                    "status": "completed",
                }

            # ----------------------------------------------
            # MODEL NODE
            # ----------------------------------------------

            if "model" in data:

                model_update = data[
                    "model"
                ]

                if not model_update:
                    continue

                messages_update = (
                    model_update.get(
                        "messages",
                        []
                    )
                )

                if not messages_update:
                    continue

                message = (
                    messages_update[-1]
                )

                tool_calls = getattr(
                    message,
                    "tool_calls",
                    []
                )

                if tool_calls:

                    for tool_call in tool_calls:

                        if not isinstance(
                            tool_call,
                            dict
                        ):
                            continue

                        tool_name = (
                            tool_call.get(
                                "name"
                            )
                            or "tool"
                        )

                        if tool_name in active_tools:
                            continue

                        active_tools[
                            tool_name
                        ] = True

                        yield {
                            "type": "tool",
                            "tool": tool_name,
                            "status": "started",
                        }


def stream_agent_text(
    agent,
    messages,
):
    """
    Convenience wrapper that yields only text.

    Useful if a caller does not need tool events.
    """

    for event in stream_agent(
        agent,
        messages
    ):

        if event.get("type") == "token":

            text = event.get(
                "text",
                ""
            )

            if text:
                yield text