# AI Customer Service & Booking Agent

An intelligent, autonomous hotel customer service assistant powered by LangGraph, LangChain, and FastAPI. It integrates deterministically enforced cancellation and refund policies with a semantic RAG policy search engine and a real-time booking management system.

---

## 🌟 Key Features

- **Autonomous Agent (LangGraph ReAct Loop)**: Handles booking queries, policy explanations, cancellations, rate calculations, and live reservations.
- **Deterministic Policy Engine**: Strict, rule-based cancellation and refund calculations according to rate plans (`FLEX`, `SEMI`, `NONREF`).
- **Policy RAG Search**: Vector/keyword-based retrieval of official policy documents and FAQs.
- **Full Hotel Booking Management**:
  - SQLite backend with seeded demo hotels and bookings.
  - Interactive web interface to browse properties, book rooms, and inspect existing reservations.
  - Real-time agent chat with tool-call inspection and policy citations.
- **Multi-Provider LLM Support**: Works seamlessly with OpenAI (`gpt-4o-mini`, etc.), Google Gemini (`gemini-2.0-flash`, etc.), or Anthropic Claude.

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
├── test_agent.py       # Pytest suite for API, policies, and tools
├── requirements.txt    # Python dependencies
├── run.sh              # Startup script with virtualenv auto-creation
├── .env.example        # Environment variable template
└── .gitignore          # Git ignore rules
```

---

## 🚀 Quick Start

### 1. Clone & Setup

```bash
git clone git@github.com:choudashu123/customer_service_agent.git
cd customer_service_agent
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure your API key (OpenAI, Google Gemini, or Anthropic):

```bash
cp .env.example .env
```

Edit `.env`:
```ini
OPENAI_API_KEY=your_openai_api_key_here
# Or GOOGLE_API_KEY=...
# Or ANTHROPIC_API_KEY=...
```

### 3. Run the Application

Execute the startup script:

```bash
chmod +x run.sh
./run.sh
```

Or run manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

The application will be accessible at: `http://localhost:8000`

---

## 🧪 Running Tests

Run the test suite to verify policy calculations, database operations, and API endpoints:

```bash
.venv/bin/python -m pytest -q
```

---

## 📄 License

MIT License.
