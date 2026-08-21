import base64
import json
import requests


def _data_url(file_bytes, mime):
    encoded = base64.b64encode(file_bytes).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def _load_attachment(fs, attachment):
    from bson import ObjectId

    f = fs.get(ObjectId(attachment["id"]))

    return f.read(), attachment["mime"]


def _build_messages(model, history, attachments, mongo_fs):
    """
    Build OpenAI-compatible messages.

    Supports:
    - normal text
    - image attachments
    - non-image attachment notices
    """

    api_messages = [
        {
            "role": item["role"],
            "content": item["content"],
        }
        for item in history
    ]

    if not api_messages:
        return api_messages

    if attachments and api_messages[-1]["role"] == "user":

        latest = api_messages[-1]

        if model.get("supports_vision"):

            parts = [
                {
                    "type": "text",
                    "text": (
                        latest["content"]
                        or "Please analyze the attached files."
                    ),
                }
            ]

            for attachment in attachments:

                raw, mime = _load_attachment(
                    mongo_fs,
                    attachment
                )

                if mime.startswith("image/"):

                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": _data_url(
                                    raw,
                                    mime
                                )
                            },
                        }
                    )

                else:

                    parts.append(
                        {
                            "type": "text",
                            "text": (
                                f"\n[Attachment: "
                                f"{attachment['name']} | "
                                f"{mime} | "
                                f"{attachment['url']}]\n"
                                "Direct analysis requires provider "
                                "support for this media type."
                            ),
                        }
                    )

            latest["content"] = parts

    return api_messages


def _endpoint(model):
    """
    Return OpenAI-compatible chat completion endpoint.
    """

    base_url = model["base_url"].rstrip("/")

    if base_url.endswith("/chat/completions"):
        return base_url

    return f"{base_url}/chat/completions"


def _headers(model):
    return {
        "Authorization": f"Bearer {model['api_key']}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }


def stream_model(
    model,
    history,
    attachments,
    mongo_fs
):
    """
    Streams an OpenAI-compatible chat completion.

    Supports:

        data: {
            "choices": [
                {
                    "delta": {
                        "content": "hello"
                    }
                }
            ]
        }

    and:

        data: {
            "choices": [
                {
                    "message": {
                        "content": "hello"
                    }
                }
            ]
        }

    Also supports plain JSON lines.
    """

    payload = {
        "model": model["model"],
        "messages": _build_messages(
            model,
            history,
            attachments,
            mongo_fs
        ),
        "temperature": 0.7,
        "stream": True,
    }

    response = requests.post(
        _endpoint(model),
        headers=_headers(model),
        json=payload,
        stream=True,
        timeout=(20, 600),
    )

    try:
        response.raise_for_status()

    except Exception:

        body = response.text[:2000]

        raise RuntimeError(
            f"Provider returned HTTP "
            f"{response.status_code}: {body}"
        )

    try:

        for raw_line in response.iter_lines(
            decode_unicode=True
        ):

            if not raw_line:
                continue

            line = raw_line.strip()

            if line.startswith("data:"):
                line = line[5:].strip()

            if line == "[DONE]":
                break

            try:
                data = json.loads(line)

            except json.JSONDecodeError:
                continue

            choices = data.get("choices") or []

            if not choices:
                continue

            choice = choices[0]

            delta = choice.get("delta") or {}

            content = delta.get("content")

            if content is None:

                message = choice.get("message") or {}

                content = message.get("content")

            if isinstance(content, str) and content:
                yield content

    finally:

        response.close()


def call_model(
    model,
    history,
    attachments,
    mongo_fs
):
    """
    Non-streaming compatibility wrapper.
    """

    return "".join(
        stream_model(
            model=model,
            history=history,
            attachments=attachments,
            mongo_fs=mongo_fs,
        )
    )