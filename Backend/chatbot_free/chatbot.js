(function () {
    "use strict";

    // ─── Public website mode (data-store-key) ─────────────────
    // Store ki website par embed (bina login visitor):
    //   <script src="https://APP/chatbot_free/chatbot.js"
    //           data-store-key="pk_..." data-api-url="https://API" async></script>
    // Visitor ka anonymous session token localStorage mein; sirf apni chat; read-only sawal-jawab.
    // data-store-key na ho to widget pehle jaisa chalta hai (logged-in / guest).

    const SCRIPT_EL =
        document.currentScript ||
        document.querySelector("script[data-store-key]");

    const STORE_KEY = SCRIPT_EL
        ? (SCRIPT_EL.getAttribute("data-store-key") || "").trim()
        : "";

    const PUBLIC_MODE = STORE_KEY.length > 0;

    // Robot image / CSS isi folder se (store ki website ka apna origin nahi)
    const ASSET_BASE = (SCRIPT_EL && SCRIPT_EL.src)
        ? SCRIPT_EL.src.split("?")[0].replace(/[^\/]*$/, "")
        : "/chatbot_free/";

    const PUBLIC_API_BASE = (
        (SCRIPT_EL && SCRIPT_EL.getAttribute("data-api-url")) ||
        window.DFTE_API_BASE ||
        ""
    ).replace(/\/+$/, "");

    const PUBLIC_CHAT_URL =
        PUBLIC_API_BASE + "/api/v1/public/stores/" +
        encodeURIComponent(STORE_KEY) + "/chat";

    const VISITOR_SESSION_KEY = "dfte_visitor_session_" + STORE_KEY;

    function getVisitorSession() {
        try {
            return localStorage.getItem(VISITOR_SESSION_KEY);
        } catch (_) {
            return null;
        }
    }

    function saveVisitorSession(token) {
        try {
            localStorage.setItem(VISITOR_SESSION_KEY, token);
        } catch (_) {
            // storage band ho to bhi chat chalti hai (is page load tak)
        }
    }

    if (PUBLIC_MODE && !document.getElementById("dfte-chatbot-css")) {

        const css = document.createElement("link");
        css.id = "dfte-chatbot-css";
        css.rel = "stylesheet";
        css.href = ASSET_BASE + "chatbot.css";
        document.head.appendChild(css);
    }

    const API_URL =
        window.DFTE_CHATBOT_API || "/chatbot/query";

    let selectedLanguage = null;
    let sending = false;

    let conversationId =
        Number(
            localStorage.getItem(
                "dfte_free_conversation_id"
            )
        ) || null;

    function getToken() {
        const possibleKeys = [
            "digital-fte-token",
            "access_token",
            "token",
            "jwt"
        ];

        for (const key of possibleKeys) {
            const token =
                localStorage.getItem(key);

            if (token) {
                return token;
            }
        }

        return null;
    }

    function createChatbot() {
        if (
            document.getElementById(
                "dfte-chatbot-root"
            )
        ) {
            return;
        }

        const root =
            document.createElement("div");

        root.id =
            "dfte-chatbot-root";

        root.innerHTML = `
            <!-- ROBOT BUTTON -->
            <button
                id="dfte-launcher"
                class="dfte-launcher"
                aria-label="Open Digital FTE chatbot"
                type="button"
            >
                <img
                    src="${ASSET_BASE}digital_fte_robot.png"
                    alt="Digital FTE AI Assistant"
                >
            </button>

            <!-- GREETING POPUP -->
            <div
                id="dfte-greeting"
                class="dfte-greeting"
            >
                Hi! &#x1F44B; How can I help you?
            </div>

            <!-- CHAT WINDOW -->
            <div
                id="dfte-window"
                class="dfte-window"
            >
                <!-- HEADER -->
                <div class="dfte-header">

                    <div class="dfte-brand">

                        <div class="dfte-logo">
                            <img
                                src="${ASSET_BASE}digital_fte_robot.png"
                                alt="Digital FTE"
                            >
                        </div>

                        <div>
                            <div class="dfte-title">
                                Digital FTE AI Assistant
                            </div>

                            <div class="dfte-status">
                                &#x25CF; Online
                            </div>
                        </div>

                    </div>

                    <button
                        id="dfte-close"
                        class="dfte-close"
                        aria-label="Close chatbot"
                        type="button"
                    >
                        &#x00D7;
                    </button>
                </div>

                <!-- BODY -->
                <div
                    id="dfte-body"
                    class="dfte-body"
                >

                    <!-- LANGUAGE SCREEN -->
                    <div
                        id="dfte-language-screen"
                        class="dfte-language-screen"
                    >
                        <h3>
                            Hi! &#x1F44B;
                        </h3>

                        <p>
                            I'm your Digital FTE AI Assistant.
                            I can answer questions about the
                            platform and your connected store.
                        </p>

                        <div
                            class="dfte-language-question"
                        >
                            Would you like to talk?

                            <span>
                                Please select your language:
                            </span>
                        </div>

                        <div
                            class="language-buttons"
                        >
                            <!-- ENGLISH -->
                            <button
                                class="dfte-language-btn"
                                data-language="english"
                                type="button"
                            >
                                <span class="flag">
                                    &#x1F1EC;&#x1F1E7;
                                </span>

                                <span>
                                    English
                                </span>
                            </button>

                            <!-- URDU -->
                            <button
                                class="dfte-language-btn"
                                data-language="urdu"
                                type="button"
                            >
                                <span class="flag">
                                    &#x1F1F5;&#x1F1F0;
                                </span>

                                <span>
                                    &#x0627;&#x0631;&#x062F;&#x0648;
                                </span>
                            </button>

                            <!-- ROMAN URDU -->
                            <button
                                class="dfte-language-btn"
                                data-language="roman_urdu"
                                type="button"
                            >
                                <span class="flag">
                                    &#x1F1F5;&#x1F1F0;
                                </span>

                                <span>
                                    Roman Urdu
                                </span>
                            </button>
                        </div>
                    </div>

                    <!-- MESSAGES -->
                    <div
                        id="dfte-messages"
                        class="dfte-messages"
                    ></div>
                </div>

                <!-- FOOTER -->
                <div
                    id="dfte-footer"
                    class="dfte-footer"
                    style="display: none;"
                >
                    <div class="dfte-input-row">

                        <textarea
                            id="dfte-input"
                            class="dfte-input"
                            rows="1"
                            placeholder="Ask something..."
                        ></textarea>

                        <button
                            id="dfte-send"
                            class="dfte-send"
                            type="button"
                            aria-label="Send message"
                        >
                            &#x27A4;
                        </button>

                    </div>

                    <div class="dfte-footer-text">
                        Free Plan · Read-only assistant
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(root);

        const launcher =
            document.getElementById(
                "dfte-launcher"
            );

        const chatWindow =
            document.getElementById(
                "dfte-window"
            );

        const greeting =
            document.getElementById(
                "dfte-greeting"
            );

        const closeButton =
            document.getElementById(
                "dfte-close"
            );

        launcher.addEventListener(
            "click",
            function () {

                chatWindow.classList.add(
                    "active"
                );

                startPolling();

                launcher.style.display =
                    "none";

                greeting.classList.add(
                    "hidden"
                );
            }
        );

        greeting.addEventListener(
            "click",
            function () {

                chatWindow.classList.add(
                    "active"
                );

                startPolling();

                launcher.style.display =
                    "none";

                greeting.classList.add(
                    "hidden"
                );
            }
        );

        closeButton.addEventListener(
            "click",
            function () {

                chatWindow.classList.remove(
                    "active"
                );

                stopPolling();

                launcher.style.display =
                    "flex";
            }
        );

        document
            .querySelectorAll(
                ".dfte-language-btn"
            )
            .forEach(
                function (button) {

                    button.addEventListener(
                        "click",
                        function () {

                            selectLanguage(
                                this.dataset.language
                            );
                        }
                    );
                }
            );

        document
            .getElementById(
                "dfte-send"
            )
            .addEventListener(
                "click",
                sendMessage
            );

        document
            .getElementById(
                "dfte-input"
            )
            .addEventListener(
                "keydown",
                function (event) {

                    if (
                        event.key === "Enter" &&
                        !event.shiftKey
                    ) {
                        event.preventDefault();
                        sendMessage();
                    }
                }
            );
    }

    function selectLanguage(language) {

        selectedLanguage =
            language;

        const languageScreen =
            document.getElementById(
                "dfte-language-screen"
            );

        const footer =
            document.getElementById(
                "dfte-footer"
            );

        const title =
            document.querySelector(
                ".dfte-title"
            );

        const status =
            document.querySelector(
                ".dfte-status"
            );

        const input =
            document.getElementById(
                "dfte-input"
            );

        languageScreen.style.display =
            "none";

        footer.style.display =
            "block";

        const welcomeMessages = {

            english:
                "Hi! \uD83D\uDC4B How can I help you today?",

            urdu:
                "\u0633\u0644\u0627\u0645 \u0639\u0644\u06CC\u06A9\u0645! \uD83D\uDC4B \u0622\u062C \u0645\u06CC\u06BA \u0622\u067E \u06A9\u06CC \u06A9\u06CC\u0633\u06D2 \u0645\u062F\u062F \u06A9\u0631 \u0633\u06A9\u062A\u0627 \u06C1\u0648\u06BA\u061F",

            roman_urdu:
                "Assalam-o-Alaikum! \uD83D\uDC4B Aaj main aapki kis tarah madad kar sakta hoon?"
        };

        const placeholders = {

            english:
                "Ask something...",

            urdu:
                "\u0627\u067E\u0646\u0627 \u0633\u0648\u0627\u0644 \u0644\u06A9\u06BE\u06CC\u06BA...",

            roman_urdu:
                "Apna sawal likhein..."
        };

        if (
            language ===
            "urdu"
        ) {

            title.textContent =
                "\u0688\u06CC\u062C\u06CC\u0679\u0644 \u0627\u06CC \u0622\u0626\u06CC \u0627\u0633\u0633\u0679\u0646\u0679";

            status.textContent =
                "\u25CF \u0622\u0646 \u0644\u0627\u0626\u0646";

            input.dir =
                "rtl";

            input.style.textAlign =
                "right";

        } else {

            title.textContent =
                "Digital FTE AI Assistant";

            status.textContent =
                "\u25CF Online";

            input.dir =
                "ltr";

            input.style.textAlign =
                "left";
        }

        input.placeholder =
            placeholders[language];

        addMessage(
            "bot",
            welcomeMessages[language]
        );
    }

    function addMessage(
        type,
        text
    ) {

        const messages =
            document.getElementById(
                "dfte-messages"
            );

        const message =
            document.createElement(
                "div"
            );

        message.className =
            "dfte-message " + type;

        const bubble =
            document.createElement(
                "div"
            );

        bubble.className =
            "dfte-bubble";

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

        message.appendChild(
            bubble
        );

        messages.appendChild(
            message
        );

        scrollToBottom();
    }

    function addTyping() {

        const messages =
            document.getElementById(
                "dfte-messages"
            );

        const message =
            document.createElement(
                "div"
            );

        message.id =
            "dfte-typing";

        message.className =
            "dfte-message bot";

        const bubble =
            document.createElement(
                "div"
            );

        bubble.className =
            "dfte-bubble";

        bubble.textContent =
            selectedLanguage === "urdu"
                ? "\u0633\u0648\u0686 \u0631\u06C1\u0627 \u06C1\u0648\u06BA..."
                : selectedLanguage === "roman_urdu"
                    ? "Soch raha hoon..."
                    : "Thinking...";

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
        }

        message.appendChild(
            bubble
        );

        messages.appendChild(
            message
        );

        scrollToBottom();
    }

    function removeTyping() {

        const typing =
            document.getElementById(
                "dfte-typing"
            );

        if (typing) {
            typing.remove();
        }
    }

    // ─── Support team replies (polling) ───────────────────────
    // Owner inbox se aaye replies: sirf jab chat khula ho, har POLL_MS par, aur tab chhupa ho to ruk jaye.

    const POLL_MS = 7000;
    let pollTimer = null;
    let polling = false;

    function lastHumanKey() {
        return "dfte_free_last_human_id_" + (PUBLIC_MODE ? STORE_KEY : conversationId);
    }

    // Poll tabhi jab polling ke liye kuch ho: public mein session token, warna conversation id
    function canPoll() {
        return PUBLIC_MODE ? !!getVisitorSession() : !!conversationId;
    }

    function chatUrl() {
        return PUBLIC_MODE ? PUBLIC_CHAT_URL : API_URL;
    }

    function pollRequest(token) {

        if (PUBLIC_MODE) {
            return fetch(
                PUBLIC_CHAT_URL + "/messages?after_id=" + getLastHumanId(),
                {
                    headers: {
                        "Accept": "application/json",
                        "X-Visitor-Session": token
                    }
                }
            );
        }

        return fetch(
            pollBase() + "/chatbot/conversations/" + conversationId +
            "/messages?after_id=" + getLastHumanId(),
            {
                headers: {
                    "Accept": "application/json",
                    "Authorization": "Bearer " + token
                }
            }
        );
    }

    function getLastHumanId() {
        return Number(localStorage.getItem(lastHumanKey())) || 0;
    }

    function chatIsOpen() {
        const chatWindow = document.getElementById("dfte-window");
        return !!chatWindow && chatWindow.classList.contains("active");
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

        const messages = document.getElementById("dfte-messages");

        const row = document.createElement("div");
        row.className = "dfte-message support";

        const wrap = document.createElement("div");
        wrap.className = "dfte-support-wrap";

        const label = document.createElement("span");
        label.className = "dfte-support-label";
        label.textContent = supportLabel();

        const bubble = document.createElement("div");
        bubble.className = "dfte-bubble";
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

        scrollToBottom();
    }

    async function pollSupportReplies() {

        if (polling || !canPoll() || !chatIsOpen() || document.hidden) {
            return;
        }

        const token = PUBLIC_MODE ? getVisitorSession() : getToken();

        if (!token) {
            return;
        }

        polling = true;

        try {

            const response = await pollRequest(token);

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

        if (pollTimer || !canPoll() || !chatIsOpen() || document.hidden) {
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

    async function sendMessage() {

        if (
            sending ||
            !selectedLanguage
        ) {
            return;
        }

        const input =
            document.getElementById(
                "dfte-input"
            );

        const sendButton =
            document.getElementById(
                "dfte-send"
            );

        const query =
            input.value.trim();

        if (!query) {
            return;
        }

        sending = true;

        sendButton.disabled =
            true;

        input.value = "";

        addMessage(
            "user",
            query
        );

        addTyping();

        try {

            const headers = {

                "Accept":
                    "application/json",

                "Content-Type":
                    "application/json"
            };

            // Public mode mein JWT kabhi nahi bheja jata (owner us browser mein login ho tab bhi)
            const token =
                PUBLIC_MODE ? null : getToken();

            if (PUBLIC_MODE && getVisitorSession()) {

                headers["X-Visitor-Session"] =
                    getVisitorSession();
            }

            if (token) {

                headers[
                    "Authorization"
                ] =
                    "Bearer " + token;
            }

            const response =
                await fetch(
                    chatUrl(),
                    {
                        method:
                            "POST",

                        headers:
                            headers,

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

            const result =
                await response.json();

            removeTyping();

            if (!response.ok) {

                throw new Error(
                    result.detail ||
                    "Chatbot request failed"
                );
            }

            conversationId =
                result.conversation_id ||
                conversationId;

            if (result.session_token) {
                saveVisitorSession(result.session_token);
            }

            if (PUBLIC_MODE) {
                startPolling();
            }

            if (conversationId) {

                localStorage.setItem(
                    "dfte_free_conversation_id",
                    String(conversationId)
                );

                startPolling();
            }

            if (!result.silent) {

                addMessage(
                    "bot",
                    result.answer ||
                    result.message ||
                    "Request processed."
                );
            }

        } catch (error) {

            removeTyping();

            const errorMessages = {

                english:
                    "Sorry, something went wrong. Please try again.",

                urdu:
                    "\u0645\u0639\u0630\u0631\u062A\u060C \u06A9\u0686\u06BE \u0645\u0633\u0626\u0644\u06C1 \u067E\u06CC\u0634 \u0622\u06CC\u0627\u06D4 \u0628\u0631\u0627\u06C1 \u06A9\u0631\u0645 \u062F\u0648\u0628\u0627\u0631\u06C1 \u06A9\u0648\u0634\u0634 \u06A9\u0631\u06CC\u06BA\u06D4",

                roman_urdu:
                    "Sorry, kuch masla hogaya. Dobara try karein."
            };

            addMessage(
                "bot",
                errorMessages[
                    selectedLanguage
                ]
            );

            console.error(
                "Digital FTE Chatbot:",
                error
            );

        } finally {

            sending = false;

            sendButton.disabled =
                false;
        }
    }

    function scrollToBottom() {

        const body =
            document.getElementById(
                "dfte-body"
            );

        body.scrollTop =
            body.scrollHeight;
    }

    if (
        document.readyState ===
        "loading"
    ) {

        document.addEventListener(
            "DOMContentLoaded",
            createChatbot
        );

    } else {

        createChatbot();
    }

})();