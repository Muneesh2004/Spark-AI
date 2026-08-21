const state = {
  chats: [],
  models: [],

  currentChatId: null,
  activeModelId: null,

  files: [],

  abortController: null,

  isGenerating: false,

  // Used to prevent an old stream from modifying
  // the currently opened chat.
  generationChatId: null
};


/* =========================
   HELPERS
   ========================= */

const $ = (id) =>
  document.getElementById(id);


async function api(url, options = {}) {

  const res = await fetch(url, options);

  const data =
    await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(
      data.error ||
      data.details ||
      "Request failed"
    );
  }

  return data;
}


/* =========================
   INITIALIZATION
   ========================= */

async function init() {

  bindEvents();

  await checkHealth();

  await loadModels();

  await loadChats();


  if (state.models.length) {

    state.activeModelId =
      state.models[0].id;

    updateModelLabel();
  }
}


/* =========================
   EVENTS
   ========================= */

function bindEvents() {

  $("newChatBtn").onclick =
    newChat;


  $("modelsBtn").onclick =
    openModels;


  $("modelsTopBtn").onclick =
    openModels;


  $("closeModal").onclick =
    closeModels;


  $("cancelModel").onclick =
    closeModels;


  $("modelForm").onsubmit =
    addModel;


  $("toggleKey").onclick =
    toggleKey;


  $("modelPicker").onclick = () => {

    $("modelMenu")
      .classList
      .toggle("open");

  };


  $("attachBtn").onclick = () =>
    $("fileInput").click();


  $("fileInput").onchange =
    handleFiles;


  $("composer").onsubmit =
    sendMessage;


  $("messageInput")
    .addEventListener(
      "input",
      autoResize
    );


  $("messageInput")
    .addEventListener(
      "keydown",
      e => {

        if (
          e.key === "Enter" &&
          !e.shiftKey
        ) {

          e.preventDefault();

          $("composer")
            .requestSubmit();
        }

      }
    );


  $("sidebarBtn").onclick = () =>
    $("sidebar")
      .classList
      .toggle("open");


  document
    .querySelectorAll(".quick-card")
    .forEach(btn => {

      btn.onclick = () => {

        $("messageInput").value =
          btn.dataset.prompt;

        autoResize();

        $("messageInput").focus();
      };

    });


  document.addEventListener(
    "click",
    e => {

      if (
        !e.target.closest(
          ".model-picker-wrap"
        )
      ) {

        $("modelMenu")
          .classList
          .remove("open");

      }

    }
  );
}


/* =========================
   DATABASE HEALTH
   ========================= */

async function checkHealth() {

  try {

    await api("/api/health");

    $("statusDot")
      .classList
      .add("ok");

    $("statusText").textContent =
      "MongoDB connected";

  } catch {

    $("statusText").textContent =
      "Database offline";
  }
}


/* =========================
   MODELS
   ========================= */

async function loadModels() {

  state.models =
    await api("/api/models");

  renderModels();
}


function renderModels() {

  const menu =
    $("modelMenu");

  menu.innerHTML = "";


  if (!state.models.length) {

    menu.innerHTML = `
      <div class="model-option">
        <span>No models configured</span>
      </div>
    `;

    return;
  }


  state.models.forEach(m => {

    const row =
      document.createElement("div");

    row.className =
      "model-option";


    row.innerHTML = `
      <span>
        ${escapeHtml(m.name)}
      </span>

      <small>
        ${escapeHtml(m.provider)}
      </small>
    `;


    row.onclick = () => {

      state.activeModelId =
        m.id;

      updateModelLabel();

      menu.classList.remove("open");
    };


    menu.appendChild(row);

  });


  $("configuredModels").innerHTML =
    state.models.map(m => `

      <div class="configured-row">

        <div>

          <strong>
            ${escapeHtml(m.name)}
          </strong>

          <span>
            ${escapeHtml(m.provider)}
            •
            ${escapeHtml(m.model)}
          </span>

        </div>

        <button
          class="delete-model"
          data-id="${m.id}"
          title="Delete"
        >
          Delete
        </button>

      </div>

    `).join("");


  document
    .querySelectorAll(".delete-model")
    .forEach(btn => {

      btn.onclick = async () => {

        if (
          !confirm(
            "Delete this model configuration?"
          )
        ) {
          return;
        }


        try {

          await api(
            `/api/models/${btn.dataset.id}`,
            {
              method:"DELETE"
            }
          );


          if (
            state.activeModelId ===
            btn.dataset.id
          ) {

            state.activeModelId =
              null;
          }


          await loadModels();

          updateModelLabel();

        } catch (err) {

          alert(
            "Failed to delete model: " +
            err.message
          );

        }

      };

    });
}


function updateModelLabel() {

  const m =
    state.models.find(
      x =>
        x.id ===
        state.activeModelId
    );


  $("activeModelName")
    .textContent =
      m
        ? m.name
        : "Select model";
}


/* =========================
   CHATS
   ========================= */

async function loadChats() {

  state.chats =
    await api("/api/chats");

  renderChats();
}


function renderChats() {

  const list =
    $("chatList");

  list.innerHTML = "";


  state.chats.forEach(chat => {

    const item =
      document.createElement("div");


    item.className =
      "chat-item" +
      (
        chat.id ===
        state.currentChatId
          ? " active"
          : ""
      );


    const title =
      document.createElement("span");

    title.className =
      "chat-title";

    title.textContent =
      chat.title ||
      "New chat";


    const deleteBtn =
      document.createElement("button");

    deleteBtn.className =
      "delete-chat";

    deleteBtn.innerHTML =
      "⋯";

    deleteBtn.title =
      "Delete chat";


    deleteBtn.onclick =
      async e => {

        e.stopPropagation();


        const confirmed =
          confirm(
            `Delete "${chat.title || "New chat"}"?\n\nThis will permanently delete the chat history.`
          );


        if (!confirmed) {
          return;
        }


        try {

          /*
           * If this chat is currently
           * generating, stop it first.
           */

          if (
            state.currentChatId ===
            chat.id &&
            state.isGenerating
          ) {

            stopGeneration();
          }


          await api(
            `/api/chats/${chat.id}`,
            {
              method:"DELETE"
            }
          );


          if (
            state.currentChatId ===
            chat.id
          ) {

            state.currentChatId =
              null;

            $("messages").innerHTML =
              "";

            $("welcome")
              .style
              .display = "";

          }


          await loadChats();

        } catch (error) {

          alert(
            "Failed to delete chat: " +
            error.message
          );

        }

      };


    item.onclick =
      () => openChat(chat.id);


    item.appendChild(title);

    item.appendChild(deleteBtn);

    list.appendChild(item);

  });
}


/* =========================
   NEW CHAT
   ========================= */

async function newChat() {

  /*
   * Stop an active generation before
   * switching to a fresh chat.
   */

  if (state.isGenerating) {
    stopGeneration();
  }


  state.currentChatId =
    null;


  state.generationChatId =
    null;


  $("messages").innerHTML =
    "";


  $("welcome")
    .style
    .display = "";


  $("messageInput").value =
    "";


  state.files = [];


  $("fileInput").value =
    "";


  renderAttachmentPreview();

  autoResize();

  renderChats();

  $("messageInput").focus();

  $("sidebar")
    .classList
    .remove("open");
}


/* =========================
   OPEN CHAT
   ========================= */

async function openChat(id) {

  /*
   * If another response is currently
   * streaming, stop it before switching.
   *
   * This prevents response A from
   * appearing inside chat B.
   */

  if (
    state.isGenerating &&
    state.currentChatId !== id
  ) {

    stopGeneration();
  }


  state.currentChatId =
    id;


  state.generationChatId =
    null;


  const messages =
    await api(
      `/api/chats/${id}/messages`
    );


  /*
   * Ignore stale loading response.
   */

  if (
    state.currentChatId !== id
  ) {

    return;
  }


  $("welcome")
    .style
    .display = "none";


  $("messages").innerHTML =
    "";


  messages.forEach(
    renderMessage
  );


  renderChats();


  $("conversation").scrollTop =
    $("conversation").scrollHeight;


  $("sidebar")
    .classList
    .remove("open");
}


/* =========================
   RENDER SAVED MESSAGE
   ========================= */

function renderMessage(msg) {

  const row =
    document.createElement("div");


  row.className =
    `message ${msg.role}`;


  const avatar =
    document.createElement("div");

  avatar.className =
    "avatar";

  avatar.textContent =
    msg.role === "user"
      ? "You"
      : "✦";


  const bubble =
    document.createElement("div");

  bubble.className =
    "bubble";


  /*
   * User messages stay plain text.
   *
   * Assistant messages use Markdown.
   */

  if (msg.role === "assistant") {

    bubble.innerHTML =
      formatText(msg.content);

  } else {

    bubble.textContent =
      msg.content || "";
  }


  if (msg.attachments?.length) {

    const wrap =
      document.createElement("div");

    wrap.className =
      "attachments";


    msg.attachments.forEach(a => {

      const chip =
        document.createElement("a");

      chip.className =
        "attachment-chip";

      chip.href =
        a.url;

      chip.target =
        "_blank";

      chip.rel =
        "noopener noreferrer";

      chip.textContent =
        `📎 ${a.name}`;


      wrap.appendChild(chip);

    });


    bubble.appendChild(wrap);
  }


  row.appendChild(avatar);

  row.appendChild(bubble);

  $("messages")
    .appendChild(row);
}


/* =========================
   TYPING
   ========================= */

function addTyping() {

  const row =
    document.createElement("div");

  row.className =
    "message assistant";

  row.id =
    "typing";


  row.innerHTML = `
    <div class="avatar">✦</div>

    <div class="bubble">

      <div class="typing">
        <i></i>
        <i></i>
        <i></i>
      </div>

    </div>
  `;


  $("messages")
    .appendChild(row);


  $("conversation").scrollTop =
    $("conversation").scrollHeight;
}


function removeTyping() {

  $("typing")?.remove();
}


/* =========================
   SEND MESSAGE
   ========================= */

async function sendMessage(e) {

  e.preventDefault();


  /*
   * If already generating,
   * the same button becomes Stop.
   */

  if (state.isGenerating) {

    stopGeneration();

    return;
  }


  const text =
    $("messageInput")
      .value
      .trim();


  if (
    !text &&
    !state.files.length
  ) {

    return;
  }


  if (!state.activeModelId) {

    openModels();

    alert(
      "Add/select a model first."
    );

    return;
  }


  $("welcome")
    .style
    .display = "none";


  const form =
    new FormData();


  form.append(
    "message",
    text
  );


  form.append(
    "model_id",
    state.activeModelId
  );


  /*
   * Existing chat = continue it.
   *
   * Null chat = backend creates
   * a brand new chat.
   */

  if (state.currentChatId) {

    form.append(
      "chat_id",
      state.currentChatId
    );
  }


  state.files.forEach(f => {

    form.append(
      "files",
      f
    );

  });


  const localAttachments =
    state.files.map(f => ({
      name:f.name,
      mime:f.type
    }));


  /*
   * Render user message immediately.
   */

  renderMessage({

    role:"user",

    content:text,

    attachments:
      localAttachments

  });


  $("messageInput").value =
    "";


  state.files = [];


  $("fileInput").value =
    "";


  renderAttachmentPreview();

  autoResize();


  /*
   * Create assistant streaming
   * message.
   */

  const assistantRow =
    createStreamingMessage();


  const bubble =
    assistantRow.querySelector(
      ".bubble"
    );


  /*
   * Fresh AbortController
   * for this generation.
   */

  state.abortController =
    new AbortController();


  /*
   * Remember which chat this stream
   * belongs to.
   */

  state.generationChatId =
    state.currentChatId;


  setGenerating(true);


  try {

    const response =
      await fetch(
        "/api/chat",
        {
          method:"POST",

          body:form,

          signal:
            state.abortController
              .signal
        }
      );


    if (!response.ok) {

      const errorData =
        await response
          .json()
          .catch(() => ({}));


      throw new Error(
        errorData.error ||
        errorData.details ||
        "Request failed"
      );
    }


    if (!response.body) {

      throw new Error(
        "Streaming is not supported by this browser."
      );
    }


    const reader =
      response.body.getReader();


    const decoder =
      new TextDecoder();


    let buffer = "";

    let answer = "";


    while (true) {

      const {
        value,
        done
      } =
        await reader.read();


      if (done) {
        break;
      }


      buffer +=
        decoder.decode(
          value,
          {
            stream:true
          }
        );


      const events =
        buffer.split("\n\n");


      buffer =
        events.pop() || "";


      for (
        const rawEvent
        of events
      ) {

        const line =
          rawEvent
            .split("\n")
            .find(
              line =>
                line.startsWith(
                  "data:"
                )
            );


        if (!line) {
          continue;
        }


        const payload =
          JSON.parse(
            line
              .slice(5)
              .trim()
          );


        /* =====================
           START
           ===================== */

        if (
          payload.type ===
          "start"
        ) {

          /*
           * Backend creates the chat
           * here when this was a new chat.
           */

          state.currentChatId =
            payload.chat_id;


          state.generationChatId =
            payload.chat_id;


          /*
           * Update sidebar immediately
           * so the new chat appears.
           */

          await loadChats()
            .catch(() => {});

        }


        /* =====================
           TOKEN
           ===================== */

        if (
          payload.type ===
          "token"
        ) {

          /*
           * Protect against an old
           * stream writing into another
           * chat.
           */

          if (
            state.generationChatId !==
            state.currentChatId
          ) {

            continue;
          }


          answer +=
            payload.text;


          /*
           * Markdown is rendered on
           * every streaming token.
           */

          bubble.innerHTML =
            formatText(answer);


          $("conversation")
            .scrollTop =
              $("conversation")
                .scrollHeight;
        }


        /* =====================
           DONE
           ===================== */

        if (
          payload.type ===
          "done"
        ) {

          state.currentChatId =
            payload.chat_id;


          /*
           * IMPORTANT:
           *
           * Stop streaming cursor.
           * Change red Stop button
           * back to white Send arrow.
           */

          assistantRow
            .classList
            .remove(
              "streaming"
            );


          setGenerating(false);

        }


        /* =====================
           ERROR
           ===================== */

        if (
          payload.type ===
          "error"
        ) {

          throw new Error(
            payload.message
          );
        }

      }

    }


    /*
     * Process final buffered SSE
     * event if one remains.
     */

    if (buffer.trim()) {

      const line =
        buffer
          .split("\n")
          .find(
            line =>
              line.startsWith(
                "data:"
              )
          );


      if (line) {

        const payload =
          JSON.parse(
            line
              .slice(5)
              .trim()
          );


        if (
          payload.type ===
          "start"
        ) {

          state.currentChatId =
            payload.chat_id;

          state.generationChatId =
            payload.chat_id;
        }


        if (
          payload.type ===
          "token"
        ) {

          answer +=
            payload.text;


          bubble.innerHTML =
            formatText(answer);
        }


        if (
          payload.type ===
          "done"
        ) {

          state.currentChatId =
            payload.chat_id;


          assistantRow
            .classList
            .remove(
              "streaming"
            );


          setGenerating(false);
        }

      }

    }


    /*
     * Empty model response.
     */

    if (!answer) {

      bubble.textContent =
        "The model returned an empty response.";
    }


    /*
     * Refresh chat title.
     *
     * This is particularly important
     * for a newly-created chat because
     * the backend generated the title
     * from the first message.
     */

    await loadChats();


  } catch (err) {

    /*
     * User intentionally stopped
     * generation.
     */

    if (
      err.name ===
      "AbortError"
    ) {

      /*
       * Keep already generated text.
       */

      if (
        !answer.trim()
      ) {

        bubble.textContent =
          "Generation stopped.";
      }


      /*
       * Remove streaming cursor.
       */

      assistantRow
        .classList
        .remove(
          "streaming"
        );


      /*
       * Restore white Send button.
       */

      setGenerating(false);


      /*
       * Backend saves the partial
       * response when stream closes.
       */

      await loadChats()
        .catch(() => {});


      return;
    }


    /*
     * Real error.
     */

    assistantRow
      .classList
      .remove(
        "streaming"
      );


    bubble.innerHTML =
      formatText(
        `**Error:** ${err.message}`
      );

  } finally {

    /*
     * Always clean up generation state.
     */

    state.abortController =
      null;

    state.generationChatId =
      null;

    setGenerating(false);


    /*
     * Make sure cursor is gone
     * even if something unexpected
     * happened.
     */

    assistantRow
      ?.classList
      .remove(
        "streaming"
      );


    $("conversation")
      .scrollTop =
        $("conversation")
          .scrollHeight;

  }
}


/* =========================
   CREATE STREAMING MESSAGE
   ========================= */

function createStreamingMessage() {

  const row =
    document.createElement("div");


  /*
   * The "streaming" class controls
   * the blinking cursor.
   *
   * It gets removed when done.
   */

  row.className =
    "message assistant streaming";


  const avatar =
    document.createElement("div");

  avatar.className =
    "avatar";

  avatar.textContent =
    "✦";


  const bubble =
    document.createElement("div");

  bubble.className =
    "bubble";


  row.appendChild(avatar);

  row.appendChild(bubble);


  $("messages")
    .appendChild(row);


  $("conversation")
    .scrollTop =
      $("conversation")
        .scrollHeight;


  return row;
}


/* =========================
   GENERATION STATE
   ========================= */

function setGenerating(
  generating
) {

  state.isGenerating =
    generating;


  const btn =
    $("sendBtn");


  if (generating) {

    /*
     * STOP STATE
     */

    btn.disabled =
      false;

    btn.innerHTML =
      "■";

    btn.title =
      "Stop generating";

    btn.classList.add(
      "stop-generating"
    );

  } else {

    /*
     * NORMAL SEND STATE
     */

    btn.disabled =
      false;

    btn.innerHTML =
      "↑";

    btn.title =
      "Send";

    btn.classList.remove(
      "stop-generating"
    );
  }
}


/* =========================
   STOP GENERATION
   ========================= */

function stopGeneration() {

  if (
    !state.abortController
  ) {

    setGenerating(false);

    return;
  }


  /*
   * Abort browser fetch.
   */

  state.abortController.abort();


  state.abortController =
    null;


  /*
   * Immediately restore Send
   * button.
   */

  setGenerating(false);
}


/* =========================
   FILES
   ========================= */

function handleFiles(e) {

  state.files =
    [...e.target.files];

  renderAttachmentPreview();
}


function renderAttachmentPreview() {

  $("attachmentPreview")
    .innerHTML =
      state.files
        .map(
          (f, i) => `

            <div class="preview">

              <span>
                📎
                ${escapeHtml(f.name)}
              </span>

              <button
                type="button"
                onclick="removeFile(${i})"
              >
                ×
              </button>

            </div>

          `
        )
        .join("");
}


window.removeFile =
  index => {

    state.files.splice(
      index,
      1
    );


    $("fileInput").value =
      "";


    renderAttachmentPreview();
  };


/* =========================
   ADD MODEL
   ========================= */

async function addModel(e) {

  e.preventDefault();


  const form =
    new FormData(
      e.target
    );


  const payload =
    Object.fromEntries(
      form.entries()
    );


  payload.supports_vision =
    form.get(
      "supports_vision"
    ) === "on";


  payload.supports_audio =
    form.get(
      "supports_audio"
    ) === "on";


  payload.supports_video =
    form.get(
      "supports_video"
    ) === "on";


  try {

    await api(
      "/api/models",
      {

        method:"POST",

        headers:{
          "Content-Type":
            "application/json"
        },

        body:
          JSON.stringify(
            payload
          )

      }
    );


    e.target.reset();


    await loadModels();


    const newest =
      state.models[0];


    if (newest) {

      state.activeModelId =
        newest.id;
    }


    updateModelLabel();

    closeModels();


  } catch(err) {

    alert(err.message);

  }
}


/* =========================
   MODAL
   ========================= */

function openModels() {

  $("modalBackdrop")
    .classList
    .remove("hidden");


  renderModels();
}


function closeModels() {

  $("modalBackdrop")
    .classList
    .add("hidden");
}


function toggleKey() {

  const input =
    document.querySelector(
      'input[name="api_key"]'
    );


  input.type =
    input.type === "password"
      ? "text"
      : "password";


  $("toggleKey")
    .textContent =
      input.type === "password"
        ? "Show"
        : "Hide";
}


/* =========================
   TEXTAREA
   ========================= */

function autoResize() {

  const el =
    $("messageInput");


  el.style.height =
    "auto";


  el.style.height =
    Math.min(
      el.scrollHeight,
      180
    ) + "px";
}


/* =========================
   MARKDOWN
   ========================= */

function formatText(text) {

  if (!text) {
    return "";
  }


  /*
   * marked converts Markdown
   * into HTML.
   */

  const html =
    marked.parse(
      String(text),
      {
        breaks:true,
        gfm:true
      }
    );


  /*
   * DOMPurify prevents unsafe
   * HTML/JS from model output.
   */

  return DOMPurify.sanitize(
    html
  );
}


/* =========================
   HTML ESCAPE
   ========================= */

function escapeHtml(s) {

  return String(s)
    .replace(
      /[&<>"']/g,
      c => ({
        "&":"&amp;",
        "<":"&lt;",
        ">":"&gt;",
        '"':"&quot;",
        "'":"&#039;"
      }[c])
    );
}


/* =========================
   START
   ========================= */

init();