import os
import re
from datetime import datetime, timezone

from bson import ObjectId
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS
from pymongo import MongoClient, DESCENDING
from gridfs import GridFS
from werkzeug.utils import secure_filename

from services.model_client import call_model, stream_model


load_dotenv()

app = Flask(__name__)
CORS(app)

# Application configuration
MAX_UPLOAD_MB = 100
DB_NAME = "spark_ai"
PORT = 5000

app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

# Secrets — loaded only from environment variables
MONGO_URI = os.getenv("MONGO_URI", "")

if not MONGO_URI:
    raise RuntimeError(
        "MONGO_URI is missing. Copy .env.example to .env and configure MongoDB Atlas."
    )

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
db = client[DB_NAME]

models_col = db["models"]
chats_col = db["chats"]
messages_col = db["messages"]
fs = GridFS(db)

ENCRYPTION_KEY = os.getenv("APP_ENCRYPTION_KEY", "").strip()

if not ENCRYPTION_KEY:
    raise RuntimeError(
        "APP_ENCRYPTION_KEY is missing. Generate a Fernet key and put it in .env."
    )

try:
    cipher = Fernet(ENCRYPTION_KEY.encode())
except Exception as exc:
    raise RuntimeError(
        "APP_ENCRYPTION_KEY is not a valid Fernet key."
    ) from exc


def encrypt_secret(value):
    return cipher.encrypt(value.encode()).decode()


def decrypt_secret(value):
    return cipher.decrypt(value.encode()).decode()


models_col.create_index("created_at")
chats_col.create_index([("updated_at", DESCENDING)])
messages_col.create_index([("chat_id", 1), ("created_at", 1)])


def now():
    return datetime.now(timezone.utc)


def serialize_model(doc):
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "provider": doc.get("provider", ""),
        "base_url": doc["base_url"],
        "model": doc["model"],
        "supports_vision": doc.get("supports_vision", False),
        "supports_audio": doc.get("supports_audio", False),
        "supports_video": doc.get("supports_video", False),
        "created_at": doc.get("created_at"),
    }


def serialize_chat(doc):
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title", "New chat"),
        "model_id": doc.get("model_id"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def make_chat_title(message):
    """Create a short, clean sidebar title from the first user message."""
    if not message:
        return "New chat"

    title = re.sub(r"\s+", " ", message.strip())

    # Remove common Markdown markers.
    title = re.sub(r"[*_`#]+", "", title).strip()

    # Remove common conversational prefixes.
    title = re.sub(
        r"^(please|can you|could you|help me|i want you to)\s+",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    if not title:
        return "New chat"

    max_length = 45

    if len(title) <= max_length:
        return title

    shortened = title[:max_length]

    if " " in shortened:
        shortened = shortened.rsplit(" ", 1)[0]

    return shortened + "..."


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    try:
        client.admin.command("ping")
        return jsonify({"ok": True, "database": DB_NAME})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/models")
def get_models():
    docs = models_col.find().sort("created_at", DESCENDING)
    return jsonify([serialize_model(d) for d in docs])


@app.post("/api/models")
def add_model():
    data = request.get_json(force=True)

    required = ["name", "provider", "base_url", "api_key", "model"]
    missing = [x for x in required if not str(data.get(x, "")).strip()]

    if missing:
        return jsonify({
            "error": f"Missing: {', '.join(missing)}"
        }), 400

    doc = {
        "name": data["name"].strip(),
        "provider": data["provider"].strip(),
        "base_url": data["base_url"].strip().rstrip("/"),
        "api_key": encrypt_secret(data["api_key"].strip()),
        "model": data["model"].strip(),
        "supports_vision": bool(data.get("supports_vision", False)),
        "supports_audio": bool(data.get("supports_audio", False)),
        "supports_video": bool(data.get("supports_video", False)),
        "created_at": now(),
    }

    result = models_col.insert_one(doc)

    return jsonify({"id": str(result.inserted_id)}), 201


@app.delete("/api/models/<model_id>")
def delete_model(model_id):
    try:
        models_col.delete_one({"_id": ObjectId(model_id)})
        return jsonify({"ok": True})
    except Exception:
        return jsonify({"error": "Invalid model id"}), 400


@app.get("/api/chats")
def get_chats():
    docs = chats_col.find().sort("updated_at", DESCENDING)
    return jsonify([serialize_chat(d) for d in docs])


@app.post("/api/chats")
def create_chat():
    data = request.get_json(silent=True) or {}

    title = make_chat_title(data.get("title", ""))

    doc = {
        "title": title,
        "model_id": data.get("model_id"),
        "created_at": now(),
        "updated_at": now(),
    }

    result = chats_col.insert_one(doc)

    return jsonify({
        "id": str(result.inserted_id),
        "title": doc["title"],
    }), 201


@app.get("/api/chats/<chat_id>/messages")
def get_messages(chat_id):
    try:
        ObjectId(chat_id)
    except Exception:
        return jsonify({"error": "Invalid chat id"}), 400

    docs = messages_col.find(
        {"chat_id": chat_id}
    ).sort("created_at", 1)

    result = []

    for d in docs:
        result.append({
            "id": str(d["_id"]),
            "role": d["role"],
            "content": d.get("content", ""),
            "attachments": d.get("attachments", []),
            "model": d.get("model"),
            "created_at": d.get("created_at"),
        })

    return jsonify(result)


@app.delete("/api/chats/<chat_id>")
def delete_chat(chat_id):
    try:
        object_id = ObjectId(chat_id)
    except Exception:
        return jsonify({"error": "Invalid chat id"}), 400

    chats_col.delete_one({"_id": object_id})
    messages_col.delete_many({"chat_id": chat_id})

    return jsonify({"ok": True})


@app.get("/api/files/<file_id>")
def get_file(file_id):
    try:
        f = fs.get(ObjectId(file_id))

        return send_file(
            f,
            mimetype=f.content_type or "application/octet-stream",
            download_name=f.filename,
            as_attachment=False,
        )

    except Exception:
        return jsonify({"error": "File not found"}), 404


@app.post("/api/chat")
def chat():
    """
    Streaming chat endpoint using Server-Sent Events (SSE).

    The browser:
      1. sends the user message
      2. receives the newly created chat_id
      3. receives model tokens immediately
      4. receives a done event
      5. backend stores the final/partial assistant response
    """

    from flask import Response, stream_with_context
    import json

    if "message" not in request.form:
        return jsonify({"error": "message is required"}), 400

    message = request.form.get("message", "").strip()
    chat_id = request.form.get("chat_id", "").strip()
    model_id = request.form.get("model_id", "").strip()

    if not model_id:
        return jsonify({"error": "Select a model first."}), 400

    try:
        model_doc = models_col.find_one({
            "_id": ObjectId(model_id)
        })
    except Exception:
        model_doc = None

    if not model_doc:
        return jsonify({"error": "Model not found."}), 404

    # Existing chat.
    if chat_id:
        try:
            chat_doc = chats_col.find_one({
                "_id": ObjectId(chat_id)
            })
        except Exception:
            chat_doc = None

        if not chat_doc:
            return jsonify({"error": "Chat not found."}), 404

        # Keep the existing chat and update its model/timestamp.
        chats_col.update_one(
            {"_id": ObjectId(chat_id)},
            {
                "$set": {
                    "model_id": model_id,
                    "updated_at": now(),
                }
            },
        )

    # New chat.
    else:
        chat_doc = {
            "title": make_chat_title(message),
            "model_id": model_id,
            "created_at": now(),
            "updated_at": now(),
        }

        chat_id = str(
            chats_col.insert_one(chat_doc).inserted_id
        )

    attachments = []
    uploaded_files = request.files.getlist("files")

    for uploaded in uploaded_files:
        if not uploaded or not uploaded.filename:
            continue

        safe_name = secure_filename(uploaded.filename)
        raw = uploaded.read()

        if not raw:
            continue

        file_id = fs.put(
            raw,
            filename=safe_name,
            content_type=uploaded.mimetype or "application/octet-stream",
            uploaded_at=now(),
            chat_id=chat_id,
        )

        attachments.append({
            "id": str(file_id),
            "name": safe_name,
            "mime": uploaded.mimetype or "application/octet-stream",
            "url": f"/api/files/{file_id}",
            "size": len(raw),
        })

    # Store user message.
    messages_col.insert_one({
        "chat_id": chat_id,
        "role": "user",
        "content": message,
        "attachments": attachments,
        "created_at": now(),
        "model": model_doc["model"],
    })

    # Get recent conversation history.
    history_docs = list(
        messages_col.find(
            {"chat_id": chat_id}
        ).sort("created_at", 1)
    )[-30:]

    history = [
        {
            "role": d["role"],
            "content": d.get("content", ""),
        }
        for d in history_docs
    ]

    safe_model = {
        **model_doc,
        "api_key": decrypt_secret(
            model_doc["api_key"]
        ),
    }

    def event(payload):
        return (
            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        )

    @stream_with_context
    def generate():
        full_answer = ""
        completed = False
        saved = False

        def save_partial():
            nonlocal saved

            if saved or not full_answer:
                return

            messages_col.insert_one({
                "chat_id": chat_id,
                "role": "assistant",
                "content": full_answer,
                "attachments": [],
                "created_at": now(),
                "model": model_doc["model"],
                "stopped": not completed,
            })

            chats_col.update_one(
                {"_id": ObjectId(chat_id)},
                {
                    "$set": {
                        "updated_at": now(),
                        "model_id": model_id,
                    }
                },
            )

            saved = True

        try:
            # Tell browser which chat this stream belongs to.
            yield event({
                "type": "start",
                "chat_id": chat_id,
                "model": model_doc["model"],
                "attachments": attachments,
            })

            # Stream provider response.
            for chunk in stream_model(
                model=safe_model,
                history=history,
                attachments=attachments,
                mongo_fs=fs,
            ):
                if chunk:
                    full_answer += chunk

                    yield event({
                        "type": "token",
                        "text": chunk,
                    })

            completed = True
            save_partial()

            yield event({
                "type": "done",
                "chat_id": chat_id,
            })

        except GeneratorExit:
            # Browser stopped/closed the stream.
            save_partial()
            raise

        except Exception as exc:
            # Save already-generated text before reporting error.
            save_partial()

            yield event({
                "type": "error",
                "message": str(exc),
                "chat_id": chat_id,
            })

        finally:
            # Ensure partial content is persisted.
            if full_answer and not saved:
                save_partial()

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.errorhandler(413)
def too_large(_):
    return jsonify({
        "error": "Upload is too large."
    }), 413


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=PORT,
        debug=True,
    )