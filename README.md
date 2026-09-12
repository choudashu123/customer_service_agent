*****References*****
Video: https://youtu.be/RiDgVbCtPdg
Github repo: https://github.com/choudashu123/customer_service_agent.git

# AI Customer Service & Booking Agent

An intelligent, autonomous hotel customer service assistant powered by LangGraph, LangChain, and FastAPI. It integrates deterministically enforced cancellation and refund policies with a semantic RAG policy search engine and a real-time booking management system.

---

## ⚡ Quick Start: Setup & Localhost Launch

Follow these steps to set up a virtual environment and run the application locally on `http://localhost:8000`.

### Prerequisites
- **Python 3.10+** ([python.org](https://www.python.org/))
- **Git** ([git-scm.com](https://git-scm.com/))

---

### 🍎 macOS & Linux

#### 1. Clone & Navigate to Project
```bash
git clone https://github.com/choudashu123/customer_service_agent.git
cd customer_service_agent
```

#### 2. Create & Activate Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` in an editor and add your API key (OpenAI, Google Gemini, or Anthropic):
```ini
OPENAI_API_KEY=your_openai_api_key_here
# or GOOGLE_API_KEY=your_gemini_api_key_here
# or ANTHROPIC_API_KEY=your_anthropic_api_key_here
```
> **Note:** The hotel catalog and booking creation work without an API key; only the AI customer service chat agent requires a key.

#### 5. Launch the Application
```bash
python3 app.py
```
*(Alternatively, you can run `./run.sh` which automatically handles venv creation, dependency installation, and server launch).*

🌐 Open your browser at: **[http://localhost:8000](http://localhost:8000)**

---

### 🪟 Windows

#### 1. Clone & Navigate to Project
```cmd
git clone https://github.com/choudashu123/customer_service_agent.git
cd customer_service_agent
```

#### 2. Create & Activate Virtual Environment
- **Command Prompt (CMD):**
  ```cmd
  python -m venv .venv
  .venv\Scripts\activate
  ```
- **PowerShell:**
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  ```
  *(If script execution is disabled in PowerShell, first run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)*

#### 3. Install Dependencies
```cmd
pip install -r requirements.txt
```

#### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
- **Command Prompt:** `copy .env.example .env`
- **PowerShell:** `Copy-Item .env.example .env`

Open `.env` in Notepad and add your API key:
```ini
OPENAI_API_KEY=your_openai_api_key_here
# or GOOGLE_API_KEY=your_gemini_api_key_here
# or ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

#### 5. Launch the Application
```cmd
python app.py
```

🌐 Open your browser at: **[http://localhost:8000](http://localhost:8000)**

---

## 🔑 LLM Provider Setup

The agent supports multiple LLM providers, checked in the following priority order:
1. `OPENAI_API_KEY` (Default model: `gpt-4o-mini`)
2. `GOOGLE_API_KEY` (Default model: `gemini-2.0-flash`)
3. `ANTHROPIC_API_KEY` (Default model: `claude-3-5-haiku-latest`)

> [!TIP]
> Free-tier Google AI Studio keys are limited to ~5 requests/min. Since an agent turn can take 2–4 requests (reasoning + tool calls), you might encounter 429 rate limit errors. If that happens, use OpenAI/Anthropic or enable pay-as-you-go billing.

---

## 🌟 Key Features

- **Autonomous Agent (LangGraph ReAct Loop)**: Handles booking queries, policy explanations, cancellations, rate calculations, and live reservations.
- **Deterministic Policy Engine**: Strict, rule-based cancellation and refund calculations according to rate plans (`FLEX`, `SEMI`, `NONREF`).
- **Policy RAG Search**: Hybrid vector and keyword retrieval over official policy documents and FAQs (`policy_docs/`).
- **Full Hotel Booking Management**:
  - SQLite backend pre-seeded with sample hotels and bookings.
  - Interactive web UI to browse properties, book rooms, and inspect existing reservations.
  - Real-time customer service chat widget with live tool-call inspection and policy citations.
- **Database Reset**: Easily reset the demo database to default state via the UI or `POST /api/reset`.

---

## 📂 Project Structure

```
├── agent.py            # LangGraph ReAct agent & tool definitions
├── app.py              # FastAPI server & REST API endpoints
├── db.py               # SQLite storage, booking schema, seed data & tool handlers
├── policy.py           # Deterministic policy & refund calculation engine
├── rag.py              # Policy document indexing & search
├── policy_docs/        # Rate plan policies and FAQ markdown files
│   ├── flexible-rate.md
│   ├── semi-flexible-rate.md
│   ├── non-refundable-rate.md
│   ├── refund-process.md
│   └── general-faq.md
├── static/             # Frontend assets (HTML, CSS, JS)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── test_agent.py       # Pytest test suite for API, policies, and tools
├── requirements.txt    # Python dependencies
├── run.sh              # Unix startup script with venv auto-creation
├── .env.example        # Environment variable template
└── .gitignore          # Git ignore rules
```

---

## 🧪 Running Tests

Run the test suite using `pytest`:

**macOS / Linux:**
```bash
pytest -q
```
*(or `.venv/bin/python -m pytest -q`)*

**Windows:**
```cmd
pytest -q
```
*(or `python -m pytest -q`)*

---

## 📄 License

MIT License.
