<div align="center">
    <img src="./asset/thoth.png"/>
    <h1>Thoth</h1>
    <h3><em>Processing truth, writing logic, and storing knowledge in eternity</em></h3>
</div>

---
<div align="center">
Thoth is an AI Agent that assist you with his knowledge — built to help engineers monitor, troubleshoot, and execute with natural commands. It understands your stack and suggests smarter workflows — all in one intelligent CLI interface.
</div>

---

## Table of Contents

- [🌙 How to run](#-How-to-run)
- [🤖 Supported LLM AI Providers](#-Supported-LLM-AI-Providers)
- [🔧 Prerequisites](#-Prerequisites)

## 🌙 How to run

### 1. Clone the Repository
Clone the repository
#### Option 1: using HTTPS
```bash
git clone https://github.com/techddt/thoth.git
cd thoth
```
<strong>OR</strong>
#### Option 2: using SSH
```bash
git clone https://github.com/techddt/thoth.git
cd thoth
```

### 2. Install dependencies and Thoth in editable modeInstall dependencies and Thoth in editable mode
```bash
uv pip install -e .
```

### 3. Activate the virtual environment
```bash
source .venv/bin/activate
```

### 4. Run Thoth
```bash
thoth
```

### 4. Run /help to see all the commands
```bash
Thoth > /help
```

## 🤖 Supported LLM AI Providers

| Provider                                                  | Support | Notes                                             |
|-----------------------------------------------------------|---------|---------------------------------------------------|
| [OpenAI](https://openai.com/api/)                          | ✅ |                                                   |
| [OpenRouter](https://openrouter.ai/)                      | ✅ |                                                   |

## 🔧 Prerequisites

- **Linux/macOS**
- [uv](https://docs.astral.sh/uv/) for package management
- [Python 3.13+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/downloads)


