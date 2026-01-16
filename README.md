# context-aware-redactor

## *Context Matters when Redacting Health Records for AI Analysis*

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Engine: Microsoft Presidio](https://img.shields.io/badge/Engine-Microsoft%20Presidio-brightgreen)](https://github.com/microsoft/presidio)
[![NLP: spaCy](https://img.shields.io/badge/NLP-spaCy-blueviolet)](https://spacy.io/)

---

## Overview

The **context-aware-redactor** is a PII/PHI redaction system specifically engineered for the complexities of Canadian healthcare documentation. Unlike standard redactors, this system understands the **syntactic and contextual relationships** within clinical narratives.

By leveraging a sophisticated **Two-Pass Recognition Pipeline**, the engine distinguishes between patients (who must be redacted) and healthcare providers or institutions (who must be preserved) to maintain the clinical utility of the de-identified data.

## Why Context Matters?

In clinical text, the same name can have different privacy implications depending on its role:

* **"John Smith** complained of pain." -> **Patient** (High Privacy Risk)
* **"Dr. John Smith** performed the surgery." -> **Provider** (Institutional Context)

Standard tools often redact both, stripping the document of its professional context and making it less useful for downstream AI analysis or clinical research. **context-aware-redactor** solves this by analyzing the grammar and surrounding keywords to make intelligent redaction decisions.

---

## Key Features

* **Canadian Healthcare Specialized**: Optimized for provincial health numbers (HCN/PHN), Canadian addresses, and clinical terminology.
* **Two-Pass Recognition Pipeline**: Discover high-confidence entities first, then use them as a "local dictionary" to find missing fragments in a second pass.
* **4-Layer Patient/Provider Defense**:
    1. **Provider Tagging**: Automatic exclusion of names preceded by healthcare titles (Dr., Nurse, etc.).
    2. **Syntactic Role Analysis**: Dependency parsing to identify PERSONs acting as patients (subjects of "complains", "reports", etc.).
    3. **Contextual Keyword Windows**: Lookbehind analysis for patient-specific markers.
    4. **Safety Checks**: Pass-2 verification to prevent accidental "leaky" redaction of providers.
* **High Performance**: Built on top of **Microsoft Presidio** and **spaCy**, with request-scoped caching for thread-safe concurrent processing.

---

## System Architecture

The system follows a layered architecture designed for extensibility and reliability.

| Layer | Component | Responsibility |
| :--- | :--- | :--- |
| **Presentation** | Streamlit UI | Interactive web interface for document testing. |
| **Service** | `RedactionService` | Singleton manager for thread-safe engine access. |
| **Engine** | `ContextAwareRedactorEngine` | Orchestrates the two-pass pipeline and result merging. |
| **Recognition** | 13+ Specialized Recognizers | Pattern and NLP-based entity detection. |
| **Domain** | `patterns.yaml` | Centralized, code-free pattern and vocabulary configuration. |

> [!TIP]
> **For detailed technical specifications, internal logic, and implementation details, see [TECH-ARCHITECTURE.md](./TECH-ARCHITECTURE.md).**

---

## Entity Types Supported

| Category | Entities |
| :--- | :--- |
| **Identity** | Patient Name, DOB, MRN, Provincial Health Numbers (All Provinces) |
| **Contact** | Phone, Email, Physical Address, Postal Code |
| **Financial** | Credit Card (Luhn validated), Bank Account, Transaction IDs |
| **Clinical** | Health Institution Names, Province Names |

---

## Getting Started

### Prerequisites

* **Python 3.12+**
* **uv** (Highly recommended for dependency management)

### Environment Setup

#### Option 1: Using `uv` (Recommended)

This project uses `uv` for fast, reproducible environment management. Installing dependencies with `uv` also automatically handles the download of the required spaCy NLP models.

1. **Clone the repository**:

   ```bash
   git clone https://github.com/your-repo/context-aware-redactor.git
   cd context-aware-redactor
   ```

2. **Initialize and sync the environment**:

   ```bash
   uv sync
   ```

   *This command creates a `.venv`, installs all dependencies, and downloads the `en_core_web_lg` model.*

#### Option 2: Using standard `venv` & `pip`

If you do not wish to use `uv`, you can set up a standard Python virtual environment:

1. **Create a virtual environment**:

   ```bash
   python -m venv .venv
   ```

2. **Activate the environment**:
   * **Windows**: `.venv\Scripts\activate`
   * **macOS/Linux**: `source .venv/bin/activate`

3. **Install dependencies**:

   ```bash
   pip install .
   ```

4. **Download the spaCy model**:

   ```bash
   python -m spacy download en_core_web_lg
   ```

### Running the Application

Launch the Streamlit interface to redact documents via your browser:

**If using `uv`:**

```bash
uv run streamlit run main.py
```

**If using a standard environment (activated):**

```bash
streamlit run main.py
```

---

## Configuration via `patterns.yaml`

The system is designed to be modified without changing Python code. You can update `redaction/core/patterns.yaml` to:

* Add new **Healthcare Titles** (e.g., specific specialist roles).
* Expand **Patient Verbs** for better subject detection.
* Define new **Patterns** for custom institution identifiers.

---

## Security & Privacy

* **Zero Leak Logging**: Structured logs strip all PII and PHI, recording only metadata (counts, lengths).
* **Request Isolation**: Uses Python `contextvars` to ensure data from one redaction request never leaks into another in concurrent environments.
* **Fail-Safe Merging**: High-confidence patterns always take precedence over discovery heuristics.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---
