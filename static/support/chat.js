const form = document.getElementById("chat-form");
const questionInput = document.getElementById("chat-question");
const sendButton = document.getElementById("chat-send");
const messageList = document.getElementById("chat-messages");
const emptyNotice = document.getElementById("chat-empty");
const statusText = document.getElementById("chat-status");

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

        summary.textContent = `${citation.title} · ${location}`;

        const passage = document.createElement("pre");
        passage.className = "document-text";
        passage.textContent = citation.text;

        details.append(summary, passage);
        article.append(details);
    }

    messageList.append(article);
}

async function loadHistory() {
    sendButton.disabled = true;

    try {
        const response = await fetch(apiUrl, {
            credentials: "same-origin",
        });

        if (!response.ok) {
            throw new Error("Could not load your conversation.");
        }

        const data = await response.json();
        messageList.replaceChildren();

        for (const message of data.messages) {
            addMessage(message);
        }
    } catch (error) {
        statusText.textContent = error.message;
    } finally {
        sendButton.disabled = false;
    }
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const content = questionInput.value.trim();
    if (!content || sendButton.disabled) return;

    sendButton.disabled = true;
    questionInput.disabled = true;
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

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error ||
                data.detail ||
                data.content?.[0] ||
                "The request failed. Please try again."
            );
        }

        for (const message of data.messages) {
            addMessage(message);
        }

        questionInput.value = "";
        statusText.textContent = "";
    } catch (error) {
        statusText.textContent = error.message;
    } finally {
        sendButton.disabled = false;
        questionInput.disabled = false;
        questionInput.focus();
    }
});

loadHistory();