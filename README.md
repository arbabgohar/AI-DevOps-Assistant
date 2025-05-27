## AI DevOps Assistant

AI DevOps Assistant is a Python-based project that combines a FastAPI backend with a React (Vite) frontend to analyze system logs and provide intelligent recommendations using OpenAI and LangChain.

---

### Features

* Analyze system logs and get AI-powered suggestions
* Monitor system health (CPU, memory, disk usage)
* Frontend built with React and Tailwind CSS
* Backend built with FastAPI and LangChain
* Easy integration with n8n for automation

---

### Technologies Used

* FastAPI, Python, LangChain, OpenAI
* React.js, Vite, Tailwind CSS
* n8n (optional for agentic workflows)

---

### Getting Started

#### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

Create a `.env` file:

```
OPENAI_API_KEY=your-openai-key
```

Run the backend:

```bash
uvicorn main:app --reload
```

#### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173` to use the dashboard.

---

### API Endpoints

| Method | Route          | Description                 |
| ------ | -------------- | --------------------------- |
| GET    | `/`            | Returns API status message  |
| GET    | `/health`      | Returns system metrics      |
| POST   | `/analyze-log` | Returns AI analysis of logs |
