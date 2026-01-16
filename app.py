from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import base64
import requests
import urllib.parse
from bs4 import BeautifulSoup
import pdfplumber
import pandas as pd
import json
app = Flask(__name__)

# =========================================================
#                     CONFIGURATION
# =========================================================

DEFAULT_API_KEY = "YourApiKey"
BASE_URL = "https://openrouter.ai/api/v1"

SYSTEM_PROMPT = """You are Chat Hub by ChippyTime, a helpful and friendly conversational assistant created by ChippyTech and provided by the chippytime.com group.

Your tone must always be friendly, casual, and helpful.
Be clear, accurate, and supportive.
When unsure, respond transparently without speculation.
"""
# =========================================================
#                 SESSION STATE INIT (FIX)
# =========================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "memory" not in st.session_state:
    st.session_state.memory = ""

st.set_page_config(
    page_title="Chat Hub",
    page_icon="Untitled drawing (3).png",
    layout="wide"
)

# =========================================================
#                     MODEL SETUP
# =========================================================

MODEL_MAP = {
    "Lite": "openai/gpt-3.5-turbo",
    "Fast": "openai/gpt-4.1",
    "Smart": "openai/gpt-4o",
    "Turbo": "openai/gpt-oss-120b"
}

image_model = "black-forest-labs/flux.2-pro"
client = OpenAI(base_url=BASE_URL, api_key=DEFAULT_API_KEY)

# =========================================================
#                     SIDEBAR
# =========================================================

st.sidebar.title("⚙️ Chat Hub Settings")

mode = st.sidebar.radio("Choose a mode", list(MODEL_MAP.keys()))
selected_model = MODEL_MAP[mode]

st.sidebar.divider()

# ================= FILE UPLOAD ============================

st.sidebar.markdown("### 📎 Upload a File")
uploaded_file = st.sidebar.file_uploader(
    "TXT, PDF, or CSV",
    type=["txt", "pdf", "csv"]
)

def read_uploaded_file(file):
    try:
        if file.type == "text/plain":
            return file.read().decode("utf-8")[:6000]

        elif file.type == "application/pdf":
            text = ""
            with pdfplumber.open(file) as pdf:
                for page in pdf.pages[:5]:
                    text += page.extract_text() or ""
            return text[:6000]

        elif file.type == "text/csv":
            df = pd.read_csv(file)
            return df.head(50).to_string()

    except Exception as e:
        return f"Error reading file: {e}"

    return None

file_context = ""
if uploaded_file:
    content = read_uploaded_file(uploaded_file)
    if content:
        file_context = f"""
The user uploaded a file. Here is its content:
{content}
"""

# ================= CHAT EXPORT ============================

st.sidebar.divider()
st.sidebar.markdown("### 💾 Export Chat")

def export_chat(fmt="txt"):
    if "messages" not in st.session_state or not st.session_state.messages:
        return "No chat history yet."

    msgs = [
        f"{m['role'].upper()}: {m['content']}"
        for m in st.session_state.messages
        if m.get("type") != "image"
    ]

    if fmt == "txt":
        return "\n\n".join(msgs)

    if fmt == "md":
        return "\n\n".join(
            f"**{m.split(':')[0]}**:{m.split(':',1)[1]}" for m in msgs
        )

    if fmt == "json":
        return json.dumps(st.session_state.messages, indent=2)

st.sidebar.download_button("Download TXT", export_chat("txt"), "chat.txt")
st.sidebar.download_button("Download Markdown", export_chat("md"), "chat.md")
st.sidebar.download_button("Download JSON", export_chat("json"), "chat.json")

# =========================================================
#                     MEMORY SYSTEM
# =========================================================

if "memory" not in st.session_state:
    st.session_state.memory = ""

def update_memory(messages):
    convo = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in messages[-6:]
        if m.get("type") != "image"
    )

    prompt = f"""
Extract long-term user preferences or goals from the conversation.
If none, return empty.

Conversation:
{convo}
"""

    try:
        resp = client.chat.completions.create(
            model="openai/gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.choices[0].message.content.strip()
    except:
        return ""

# =========================================================
#                     WEB SCRAPER
# =========================================================

def get_headers():
    return {"User-Agent": "Mozilla/5.0"}

def url_reader(url):
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer"]):
            tag.extract()

        text = soup.get_text("\n")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return "\n".join(lines)[:6000], None
    except Exception as e:
        return None, str(e)

# =========================================================
#                     MAIN UI
# =========================================================

st.title("🤖 Chat Hub")
st.caption("Your personal AI assistant by ChippyTime")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("type") == "image":
            st.image(msg["content"])
        else:
            st.markdown(msg["content"])

# =========================================================
#                     CHAT INPUT
# =========================================================

prompt = st.chat_input("Ask me anything, or type /help")

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)

    st.session_state.messages.append(
        {"role": "user", "content": prompt}
    )

    # ================= /IMAGE =============================

    if prompt.startswith("/image"):
        img_prompt = prompt.replace("/image", "", 1).strip()
        with st.chat_message("assistant"):
            with st.spinner("🎨 Generating image..."):
                resp = client.chat.completions.create(
                    model=image_model,
                    messages=[{"role": "user", "content": img_prompt}],
                    extra_body={"modalities": ["image", "text"]}
                )
                img_data = resp.choices[0].message.images[0]["image_url"]["url"]
                img_bytes = base64.b64decode(img_data.split(",")[1])
                st.image(img_bytes)
                st.session_state.messages.append(
                    {"role": "assistant", "type": "image", "content": img_bytes}
                )
        st.stop()

    # ================= /READ ==============================

    if prompt.startswith("/read"):
        url = prompt.replace("/read", "", 1).strip()
        with st.chat_message("assistant"):
            with st.spinner("📖 Reading webpage..."):
                content, err = url_reader(url)
                if err:
                    st.error(err)
                    st.stop()

                summary_prompt = f"""
Summarize the key points of the following webpage:

{content}
"""

                resp = client.chat.completions.create(
                    model=selected_model,
                    messages=[{"role": "user", "content": summary_prompt}]
                )

                reply = resp.choices[0].message.content
                st.markdown(reply)
                st.session_state.messages.append(
                    {"role": "assistant", "content": reply}
                )
        st.stop()

    # ================= /HELP ==============================

    if prompt.startswith("/help"):
        help_text = """
### Commands
- `/image <prompt>` – Generate AI art
- `/read <url>` – Read & summarize a webpage
- Upload a file to chat with documents
"""
        with st.chat_message("assistant"):
            st.markdown(help_text)
        st.session_state.messages.append(
            {"role": "assistant", "content": help_text}
        )
        st.stop()

    # ================= NORMAL CHAT ========================

    memory_block = (
        f"User memory:\n{st.session_state.memory}"
        if st.session_state.memory else ""
    )

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""

        stream = client.chat.completions.create(
            model=selected_model,
            stream=True,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "system", "content": memory_block},
                {"role": "system", "content": file_context},
                *st.session_state.messages
            ]
        )

        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            full_response += delta
            placeholder.markdown(full_response + " ⬤")

        placeholder.markdown(full_response)

    st.session_state.messages.append(
        {"role": "assistant", "content": full_response}
    )

    # Update memory
    new_memory = update_memory(st.session_state.messages)
    if new_memory:
        st.session_state.memory = new_memory
