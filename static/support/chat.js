const form = document.getElementById("chat-form");
const questionInput = document.getElementById("chat-question");
const sendButton = document.getElementById("chat-send");
const reloadButton = document.getElementById("chat-reload");
const messageList = document.getElementById("chat-messages");
const emptyNotice = document.getElementById("chat-empty");
const statusText = document.getElementById("chat-status");

let historyLoaded = false;

const apiUrl = form.dataset.apiUrl;
const csrfToken = form.querySelector(
    '[name="csrfmiddlewaretoken"]'
).value;

function addMessage(message) {
    emptyNotice.hidden = true;

    const article = document.createElement("article");
    article.className = `chat-message ${message.role}`;

    const heading = document.createElement("h3");
    heading.textContent =
        message.role === "user" ? "You" : "Assistant";

    const content = document.createElement("p");
    content.className = "chat-content";
    content.textContent = message.content;

    article.append(heading, content);

    for (const citation of message.citations) {
        const details = document.createElement("details");
        const summary = document.createElement("summary");

        const location = citation.is_txt
            ? "Text document"
            : `Page ${citation.page_number}`;

        const version = citation.document_version
            ? `v${citation.document_version}`
            : "Version not recorded";

        summary.textContent =
            `${citation.title} · ${version} · ${location}`;

        const passage = document.createElement("pre");
        passage.className = "document-text";
        passage.textContent = citation.text;

        details.append(summary, passage);
        article.append(details);
    }

    messageList.append(article);
}

function scrollToLatest() {
    messageList.scrollTop = messageList.scrollHeight;
}

async function readResponse(response) {
    try {
        return await response.json();
    } catch {
        throw new Error(
            "The request could not be completed. " +
            "Please reload the conversation."
        );
    }
}

async function loadHistory() {
    historyLoaded = false;
    sendButton.disabled = true;
    reloadButton.disabled = true;
    statusText.textContent = "Loading conversation…";

    try {
        const response = await fetch(apiUrl, {
            credentials: "same-origin",
        });

        if (!response.ok) {
            throw new Error("Could not load your conversation.");
        }

        const data = await readResponse(response);

        if (!Array.isArray(data.messages)) {
            throw new Error("Could not load your conversation.");
        }

        messageList.replaceChildren();
        emptyNotice.hidden = data.messages.length > 0;

        for (const message of data.messages) {
            addMessage(message);
        }

        historyLoaded = true;
        scrollToLatest();
        statusText.textContent = "";

    } catch (error) {
        statusText.textContent = error.message;

    } finally {
        sendButton.disabled = !historyLoaded;
        reloadButton.disabled = false;
    }

    return historyLoaded;
}

reloadButton.addEventListener("click", loadHistory);

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const content = questionInput.value.trim();
    if (!content || sendButton.disabled) return;

    sendButton.disabled = true;
    questionInput.disabled = true;
    reloadButton.disabled = true;
    statusText.textContent = "Finding an answer…";

    try {
        const response = await fetch(apiUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
            },
            body: JSON.stringify({ content }),
        });

        const data = await readResponse(response);

        if (!response.ok) {
            throw new Error(
                data.error ||
                data.detail ||
                data.content?.[0] ||
                "The request failed. Please try again."
            );
        }

        if (!Array.isArray(data.messages)) {
            throw new Error(
                "The reply could not be displayed. " +
                "Please reload the conversation."
            );
        }

        for (const message of data.messages) {
            addMessage(message);
        }

        scrollToLatest();
        questionInput.value = "";
        statusText.textContent = "";

    } catch (error) {
        const errorMessage = error instanceof TypeError
            ? "The connection was interrupted."
            : error.message;

        // Refresh history without automatically resending the question.
        const refreshed = await loadHistory();

        statusText.textContent = errorMessage + (
            refreshed
                ? ""
                : " Reload the conversation before trying again."
        );

    } finally {
        sendButton.disabled = !historyLoaded;
        reloadButton.disabled = false;
        questionInput.disabled = false;
        questionInput.focus();
    }
});

loadHistory();