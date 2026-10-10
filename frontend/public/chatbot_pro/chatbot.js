(function () {
    "use strict";

    const API_URL =
        window.DFTE_PRO_CHATBOT_API || "/agent/query";

    const ROBOT_URL =
        window.DFTE_PRO_ROBOT_URL ||
        "/chatbot_pro/digital_fte_robot.png";

    let selectedLanguage = null;

    let conversationId =
        Number(
            localStorage.getItem(
                "dfte_pro_conversation_id"
            )
        ) || null;

    // =========================================================
    // UNICODE HELPER
    // =========================================================

    function U(...codes) {
        return String.fromCodePoint(...codes);
    }

    const HAND = U(0x1F44B);
    const ENGLISH_FLAG = U(0x1F1EC, 0x1F1E7);
    const PAKISTAN_FLAG = U(0x1F1F5, 0x1F1F0);
    const BULLET = U(0x25CF);
    const CLOSE = U(0x00D7);
    const SEND = U(0x27A4);

    // =========================================================
    // URDU TEXT
    // =========================================================

    const URDU = {

        label:
            U(
                0x0627,
                0x0631,
                0x062F,
                0x0648
            ),

        welcome:
            U(
                0x0633, 0x0644, 0x0627, 0x0645,
                0x0020,
                0x0639, 0x0644, 0x06CC, 0x06A9, 0x0645,
                0x0021,
                0x0020,
                0x1F44B,
                0x0020,
                0x0645, 0x06CC, 0x06BA,
                0x0020,
                0x0622, 0x067E,
                0x0020,
                0x06A9, 0x0627,
                0x0020,
                0x0688, 0x06CC, 0x062C, 0x06CC, 0x0679, 0x0644,
                0x0020,
                0x0627, 0x06CC, 0x0641,
                0x0020,
                0x0679, 0x06CC, 0x0020,
                0x0627, 0x06CC,
                0x0020,
                0x067E, 0x0631, 0x0648,
                0x0020,
                0x0627, 0x06CC, 0x062C, 0x0646, 0x0679,
                0x0020,
                0x06C1, 0x0648, 0x06BA,
                0x06D4,
                0x0020,
                0x0628, 0x062A, 0x0627, 0x0626, 0x06CC, 0x06D2,
                0x060C,
                0x0020,
                0x0622, 0x067E,
                0x0020,
                0x0627, 0x067E, 0x0646, 0x06D2,
                0x0020,
                0x0645, 0x0646, 0x0633, 0x0644, 0x06A9,
                0x0020,
                0x0627, 0x0633, 0x0679, 0x0648, 0x0631,
                0x0020,
                0x0645, 0x06CC, 0x06BA,
                0x0020,
                0x06A9, 0x06CC, 0x0627,
                0x0020,
                0x06A9, 0x0631, 0x0648, 0x0627, 0x0646, 0x0627,
                0x0020,
                0x0686, 0x0627, 0x06C1, 0x062A, 0x06D2,
                0x0020,
                0x06C1, 0x06CC, 0x06BA,
                0x061F
            ),

        thinking:
            U(
                0x0633, 0x0648, 0x0686,
                0x0020,
                0x0631, 0x06C1, 0x0627,
                0x0020,
                0x06C1, 0x0648, 0x06BA,
                0x002E, 0x002E, 0x002E
            ),

        login:
            U(
                0x067E, 0x0631, 0x0648,
                0x0020,
                0x067E, 0x0644, 0x0627, 0x0646,
                0x0020,
                0x06A9, 0x06CC,
                0x0020,
                0x06A9, 0x0627, 0x0631, 0x0631, 0x0648, 0x0627, 0x0626, 0x06CC, 0x0627, 0x06BA,
                0x0020,
                0x0627, 0x0633, 0x062A, 0x0639, 0x0645, 0x0627, 0x0644,
                0x0020,
                0x06A9, 0x0631, 0x0646, 0x06D2,
                0x0020,
                0x06A9, 0x06D2,
                0x0020,
                0x0644, 0x06CC, 0x06D2,
                0x0020,
                0x067E, 0x06C1, 0x0644, 0x06D2,
                0x0020,
                0x0644, 0x0627, 0x06AF,
                0x0020,
                0x0627, 0x0653, 0x0646,
                0x0020,
                0x06A9, 0x0631, 0x06CC, 0x06BA,
                0x06D4
            ),

        error:
            U(
                0x067E, 0x0631, 0x0648,
                0x0020,
                0x0627, 0x06CC, 0x062C, 0x0646, 0x0679,
                0x0020,
                0x0633, 0x06D2,
                0x0020,
                0x0631, 0x0627, 0x0628, 0x0637, 0x06C1,
                0x0020,
                0x0646, 0x06C1, 0x06CC, 0x06BA,
                0x0020,
                0x06C1, 0x0648,
                0x0020,
                0x0633, 0x06A9, 0x0627,
                0x06D4,
                0x0020,
                0x0628, 0x0631, 0x0627, 0x06C1,
                0x0020,
                0x06A9, 0x0631, 0x0645,
                0x0020,
                0x0628, 0x06CC, 0x06A9,
                0x0020,
                0x0627, 0x06CC, 0x0646, 0x0688,
                0x0020,
                0x0686, 0x06CC, 0x06A9,
                0x0020,
                0x06A9, 0x0631, 0x06CC, 0x06BA,
                0x06D4
            )
    };

    // =========================================================
    // JWT
    // =========================================================

    function getToken() {
        return (
            localStorage.getItem("digital-fte-access-token") ||
            localStorage.getItem("access_token") ||
            localStorage.getItem("token") ||
            sessionStorage.getItem("access_token") ||
            sessionStorage.getItem("token")
        );
    }

    // =========================================================
    // CREATE CHATBOT
    // =========================================================

    const root =
        document.createElement("div");

    root.id =
        "dfte-pro-chatbot-root";

    root.innerHTML = `
        <!-- GREETING POPUP -->
        <div class="dfte-pro-launcher-message">
            <span>
                Hi! ${HAND}
            </span>

            <small>
                How may I help you?
            </small>
        </div>

        <!-- ROBOT LAUNCHER -->
        <button
            class="dfte-pro-launcher"
            aria-label="Open Digital FTE Pro Agent"
            type="button"
        >
            <img
                src="${ROBOT_URL}"
                alt="Digital FTE Pro Agent"
            >
        </button>

        <!-- CHAT WINDOW -->
        <div
            class="dfte-pro-window"
            aria-hidden="true"
        >

            <!-- HEADER -->
            <header class="dfte-pro-header">

                <div class="dfte-pro-brand">

                    <div class="dfte-pro-logo">

                        <img
                            src="${ROBOT_URL}"
                            alt="Digital FTE Pro Agent"
                        >

                    </div>

                    <div>

                        <div class="dfte-pro-title">
                            Digital FTE Pro Agent
                        </div>

                        <div class="dfte-pro-status">
                            ${BULLET} Online
                        </div>

                    </div>

                </div>

                <button
                    class="dfte-pro-close"
                    aria-label="Close chatbot"
                    type="button"
                >
                    ${CLOSE}
                </button>

            </header>

            <!-- BODY -->
            <main class="dfte-pro-body">

                <!-- LANGUAGE SCREEN -->
                <div class="dfte-pro-language-screen">

                    <div class="dfte-pro-welcome-avatar">
                        <img
                            src="${ROBOT_URL}"
                            alt="Digital FTE"
                        >
                    </div>

                    <h2>
                        Hi! ${HAND}
                    </h2>

                    <p>
                        I'm your Digital FTE Pro Agent.
                        I can help you perform authorized
                        actions on your connected store.
                    </p>

                    <div
                        class="dfte-pro-language-question"
                    >

                        Would you like to talk?

                        <span>
                            Please select your language:
                        </span>

                    </div>

                    <div
                        class="dfte-pro-language-buttons"
                    >

                        <!-- ENGLISH -->
                        <button
                            class="dfte-pro-language-btn"
                            data-language="english"
                            type="button"
                        >

                            <span class="flag">
                                ${ENGLISH_FLAG}
                            </span>

                            <span>
                                English
                            </span>

                        </button>

                        <!-- URDU -->
                        <button
                            class="dfte-pro-language-btn"
                            data-language="urdu"
                            type="button"
                        >

                            <span class="flag">
                                ${PAKISTAN_FLAG}
                            </span>

                            <span>
                                ${URDU.label}
                            </span>

                        </button>

                        <!-- ROMAN URDU -->
                        <button
                            class="dfte-pro-language-btn"
                            data-language="roman_urdu"
                            type="button"
                        >

                            <span class="flag">
                                ${PAKISTAN_FLAG}
                            </span>

                            <span>
                                Roman Urdu
                            </span>

                        </button>

                    </div>

                </div>

                <!-- CHAT SCREEN -->
                <div
                    class="dfte-pro-chat-screen"
                >

                    <div
                        class="dfte-pro-messages"
                    ></div>

                </div>

            </main>

            <!-- FOOTER -->
            <footer class="dfte-pro-footer">

                <div
                    class="dfte-pro-input-row"
                >

                    <textarea
                        class="dfte-pro-input"
                        rows="1"
                        placeholder="Tell me what you want me to do..."
                    ></textarea>

                    <button
                        class="dfte-pro-send"
                        aria-label="Send message"
                        type="button"
                    >
                        ${SEND}
                    </button>

                </div>

                <div
                    class="dfte-pro-footer-text"
                >
                    Digital FTE Pro - AI Agent
                </div>

            </footer>

        </div>
    `;

    document.body.appendChild(root);

    const launcher =
        root.querySelector(
            ".dfte-pro-launcher"
        );

    const launcherMessage =
        root.querySelector(
            ".dfte-pro-launcher-message"
        );

    const windowEl =
        root.querySelector(
            ".dfte-pro-window"
        );

    const closeButton =
        root.querySelector(
            ".dfte-pro-close"
        );

    const languageScreen =
        root.querySelector(
            ".dfte-pro-language-screen"
        );

    const chatScreen =
        root.querySelector(
            ".dfte-pro-chat-screen"
        );

    const languageButtons =
        root.querySelectorAll(
            ".dfte-pro-language-btn"
        );

    const input =
        root.querySelector(
            ".dfte-pro-input"
        );

    const sendButton =
        root.querySelector(
            ".dfte-pro-send"
        );

    const messages =
        root.querySelector(
            ".dfte-pro-messages"
        );

    // =========================================================
    // ADD MESSAGE
    // =========================================================

    function addMessage(
        text,
        type
    ) {

        const row =
            document.createElement(
                "div"
            );

        row.className =
            "dfte-pro-message " +
            type;

        const bubble =
            document.createElement(
                "div"
            );

        bubble.className =
            "dfte-pro-bubble";

        bubble.textContent =
            text;

        if (
            selectedLanguage ===
            "urdu"
        ) {

            bubble.dir =
                "rtl";

            bubble.style.direction =
                "rtl";

            bubble.style.textAlign =
                "right";

        } else {

            bubble.dir =
                "ltr";

            bubble.style.direction =
                "ltr";

            bubble.style.textAlign =
                "left";
        }

        row.appendChild(
            bubble
        );

        messages.appendChild(
            row
        );

        messages.scrollTop =
            messages.scrollHeight;
    }

    // =========================================================
    // OPEN / CLOSE
    // =========================================================

    // ─── Support team replies (polling) ───────────────────────
    // Owner inbox se aaye replies: sirf jab chat khula ho, har POLL_MS par, aur tab chhupa ho to ruk jaye.

    const POLL_MS = 7000;
    let pollTimer = null;
    let polling = false;

    function lastHumanKey() {
        return "dfte_pro_last_human_id_" + conversationId;
    }

    function getLastHumanId() {
        return Number(localStorage.getItem(lastHumanKey())) || 0;
    }

    function chatIsOpen() {
        return windowEl.classList.contains("active");
    }

    function pollBase() {
        return API_URL.replace(/\/(agent|chatbot)\/query\/?$/, "");
    }

    function supportLabel() {
        return selectedLanguage === "urdu"
            ? "\u0633\u067E\u0648\u0631\u0679 \u0679\u06CC\u0645"
            : "Support team";
    }

    function addSupportMessage(text) {

        const row = document.createElement("div");
        row.className = "dfte-pro-message support";

        const wrap = document.createElement("div");
        wrap.className = "dfte-pro-support-wrap";

        const label = document.createElement("span");
        label.className = "dfte-pro-support-label";
        label.textContent = supportLabel();

        const bubble = document.createElement("div");
        bubble.className = "dfte-pro-bubble";
        bubble.textContent = text;

        if (selectedLanguage === "urdu") {
            bubble.dir = "rtl";
            bubble.style.direction = "rtl";
            bubble.style.textAlign = "right";
        } else {
            bubble.dir = "ltr";
            bubble.style.direction = "ltr";
            bubble.style.textAlign = "left";
        }

        wrap.appendChild(label);
        wrap.appendChild(bubble);
        row.appendChild(wrap);
        messages.appendChild(row);
        messages.scrollTop = messages.scrollHeight;
    }

    async function pollSupportReplies() {

        if (polling || !conversationId || !chatIsOpen() || document.hidden) {
            return;
        }

        const jwt = getToken();

        if (!jwt) {
            return;
        }

        polling = true;

        try {

            const response = await fetch(
                pollBase() + "/chatbot/conversations/" + conversationId +
                "/messages?after_id=" + getLastHumanId(),
                {
                    headers: {
                        "Accept": "application/json",
                        "Authorization": "Bearer " + jwt
                    }
                }
            );

            if (response.status === 401 || response.status === 404) {
                stopPolling();
                return;
            }

            if (!response.ok) {
                return;
            }

            const data = await response.json();

            (data.messages || []).forEach(function (m) {

                if (m.id > getLastHumanId()) {
                    addSupportMessage(m.content);
                    localStorage.setItem(lastHumanKey(), String(m.id));
                }
            });

        } catch (_) {
            // network blip — agli baar dobara
        } finally {
            polling = false;
        }
    }

    function startPolling() {

        if (pollTimer || !conversationId || !chatIsOpen() || document.hidden) {
            return;
        }

        pollSupportReplies();
        pollTimer = setInterval(pollSupportReplies, POLL_MS);
    }

    function stopPolling() {

        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    document.addEventListener("visibilitychange", function () {

        if (document.hidden) {
            stopPolling();
        } else {
            startPolling();
        }
    });

    function openChat() {
        openChatWindow();
        startPolling();
    }

    function openChatWindow() {

        windowEl.classList.add(
            "active"
        );

        windowEl.setAttribute(
            "aria-hidden",
            "false"
        );

        launcherMessage.classList.remove(
            "show"
        );
    }

    function closeChat() {
        stopPolling();
        closeChatWindow();
    }

    function closeChatWindow() {

        windowEl.classList.remove(
            "active"
        );

        windowEl.setAttribute(
            "aria-hidden",
            "true"
        );
    }

    // =========================================================
    // LANGUAGE SELECT
    // =========================================================

    languageButtons.forEach(
        (button) => {

            button.addEventListener(
                "click",
                () => {

                    selectedLanguage =
                        button.dataset.language;

                    languageScreen.style.display =
                        "none";

                    chatScreen.classList.add(
                        "active"
                    );

                    if (
                        !messages.children.length
                    ) {

                        let message;

                        if (
                            selectedLanguage ===
                            "urdu"
                        ) {

                            message =
                                URDU.welcome;

                        } else if (
                            selectedLanguage ===
                            "roman_urdu"
                        ) {

                            message =
                                "Assalam-o-Alaikum! " +
                                HAND +
                                " Main aapka Digital FTE Pro Agent hoon. Batayein aap apne connected store mein kya karwana chahte hain?";

                        } else {

                            message =
                                "Hi! " +
                                HAND +
                                " I'm your Digital FTE Pro Agent. Tell me what you'd like me to do, and I'll handle it for you.";
                        }

                        addMessage(
                            message,
                            "bot"
                        );
                    }

                    if (
                        selectedLanguage ===
                        "urdu"
                    ) {

                        input.dir =
                            "rtl";

                        input.style.direction =
                            "rtl";

                        input.style.textAlign =
                            "right";

                    } else {

                        input.dir =
                            "ltr";

                        input.style.direction =
                            "ltr";

                        input.style.textAlign =
                            "left";
                    }

                    input.focus();
                }
            );
        }
    );

    // =========================================================
    // SEND MESSAGE
    // =========================================================

    async function sendMessage() {

        const query =
            input.value.trim();

        if (!query) {
            return;
        }

        if (!selectedLanguage) {
            return;
        }

        const jwt =
            getToken();

        // -----------------------------------------------------
        // LOGIN REQUIRED
        // -----------------------------------------------------

        if (!jwt) {

            let loginMessage;

            if (
                selectedLanguage ===
                "urdu"
            ) {

                loginMessage =
                    URDU.login;

            } else if (
                selectedLanguage ===
                "roman_urdu"
            ) {

                loginMessage =
                    "Pro Plan ki actions use karne ke liye pehle login karein.";

            } else {

                loginMessage =
                    "Please log in first to use Pro Plan store actions.";
            }

            addMessage(
                loginMessage,
                "bot"
            );

            return;
        }

        // -----------------------------------------------------
        // USER MESSAGE
        // -----------------------------------------------------

        addMessage(
            query,
            "user"
        );

        input.value = "";

        sendButton.disabled =
            true;

        // -----------------------------------------------------
        // THINKING
        // -----------------------------------------------------

        const typing =
            document.createElement(
                "div"
            );

        typing.className =
            "dfte-pro-message bot";

        const typingBubble =
            document.createElement(
                "div"
            );

        typingBubble.className =
            "dfte-pro-bubble";

        typingBubble.textContent =
            selectedLanguage === "urdu"
                ? URDU.thinking
                : selectedLanguage === "roman_urdu"
                    ? "Soch raha hoon..."
                    : "Thinking...";

        if (
            selectedLanguage ===
            "urdu"
        ) {

            typingBubble.dir =
                "rtl";

            typingBubble.style.direction =
                "rtl";

            typingBubble.style.textAlign =
                "right";
        }

        typing.appendChild(
            typingBubble
        );

        messages.appendChild(
            typing
        );

        messages.scrollTop =
            messages.scrollHeight;

        // -----------------------------------------------------
        // API REQUEST
        // -----------------------------------------------------

        try {

            const response =
                await fetch(
                    API_URL,
                    {
                        method:
                            "POST",

                        headers: {

                            "Accept":
                                "application/json",

                            "Content-Type":
                                "application/json",

                            "Authorization":
                                "Bearer " +
                                jwt
                        },

                        body:
                            JSON.stringify({

                                query:
                                    query,

                                preferred_language:
                                    selectedLanguage,

                                conversation_id:
                                    conversationId
                            })
                    }
                );

            const raw =
                await response.text();

            let data = {};

            try {

                data =
                    JSON.parse(
                        raw
                    );

            } catch (_) {

                data = {};
            }

            typing.remove();

            // -------------------------------------------------
            // ERROR
            // -------------------------------------------------

            if (!response.ok) {

                const errorMessage =
                    data.detail ||

                    (
                        selectedLanguage ===
                        "urdu"

                            ? URDU.error

                            : selectedLanguage ===
                              "roman_urdu"

                                ? "Pro Agent ye request complete nahi kar saka."

                                : "The Pro Agent could not process this request."
                    );

                addMessage(
                    errorMessage,
                    "bot"
                );

                return;
            }

            // -------------------------------------------------
            // SAVE CONVERSATION
            // -------------------------------------------------

            conversationId =
                data.conversation_id ||
                conversationId;

            if (conversationId) {

                localStorage.setItem(
                    "dfte_pro_conversation_id",
                    String(conversationId)
                );

                startPolling();
            }

            // -------------------------------------------------
            // SUCCESS
            // -------------------------------------------------

            const answer =
                data.answer ||
                data.message;

            if (answer) {

                addMessage(
                    answer,
                    "bot"
                );

            } else if (!data.silent) {

                addMessage(
                    selectedLanguage ===
                        "urdu"

                        ? U(
                            0x062F, 0x0631, 0x062E, 0x0648, 0x0627, 0x0633, 0x062A,
                            0x0020,
                            0x06A9, 0x0627, 0x0645, 0x06CC, 0x0627, 0x0628, 0x06CC,
                            0x0020,
                            0x0633, 0x06D2,
                            0x0020,
                            0x0645, 0x06A9, 0x0645, 0x0644,
                            0x0020,
                            0x06C1, 0x0648,
                            0x0020,
                            0x06AF, 0x0626, 0x06CC,
                            0x06D4
                        )

                        : selectedLanguage ===
                          "roman_urdu"

                            ? "Request successfully process ho gayi."

                            : "Request processed successfully.",
                    "bot"
                );
            }

        } catch (error) {

            typing.remove();

            let errorMessage;

            if (
                selectedLanguage ===
                "urdu"
            ) {

                errorMessage =
                    URDU.error;

            } else if (
                selectedLanguage ===
                "roman_urdu"
            ) {

                errorMessage =
                    "Pro Agent se connection nahi ho saka. Backend check karein.";

            } else {

                errorMessage =
                    "Could not connect to the Pro Agent. Please check the backend.";
            }

            addMessage(
                errorMessage,
                "bot"
            );

            console.error(
                "Digital FTE Pro Agent:",
                error
            );

        } finally {

            sendButton.disabled =
                false;

            input.focus();
        }
    }

    // =========================================================
    // EVENTS
    // =========================================================

    launcher.addEventListener(
        "click",
        openChat
    );

    closeButton.addEventListener(
        "click",
        closeChat
    );

    sendButton.addEventListener(
        "click",
        sendMessage
    );

    input.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key === "Enter" &&
                !event.shiftKey
            ) {

                event.preventDefault();

                sendMessage();
            }
        }
    );

    // =========================================================
    // SHOW GREETING POPUP
    // =========================================================

    setTimeout(
        () => {

            launcherMessage.classList.add(
                "show"
            );

        },
        800
    );

})();
