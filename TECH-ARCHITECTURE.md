# Context Aware Redactor - Comprehensive Architecture Document

## 1. Executive Summary

This document provides a definitive technical architecture guide for the **Context Aware Redactor** system. The system automatically detects and redacts Personal Identifiable Information (PII) and Personal Health Information (PHI) from clinical documents while intelligently preserving Healthcare Provider Names and institutional information.

The key architectural innovation is the **Two-Pass Recognition Pipeline** combined with **Multi-Layer Patient vs. Provider Distinction Logic**. This approach ensures that only patient information is redacted while healthcare provider and institutional names are preserved, critical for maintaining clinical document integrity.

This architecture is designed to be maintainable, extensible, and safe by enforcing clear separation of concerns across multiple layers. Future enhancements, integrations, and modifications must respect these architectural boundaries to avoid breaking core functionality.

---

## 2. System Architecture Overview

The system follows a **layered microservice-oriented architecture** with five distinct logical layers:

```
┌─────────────────────────────────────────────────────────────┐
│         Presentation Layer (Streamlit UI)                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Service Layer (RedactionService - Singleton Pattern)       │
│  - Thread-safe engine lifecycle management                  │
│  - Request routing & error handling                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ Engine Layer (ContextAwareRedactorEngine)                   │
│ - Two-Pass Recognition Pipeline                             │
│ - Result Merging & De-duplication                           │
│ - Anonymization Coordination                                │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ Recognition & NLP Layer                                     │
│ - Recognizer Registry (13 specialized recognizers)          │
│ - CanadianClinicalNlpEngine (spaCy with custom components)  │
│ - Cache Management (Request-scoped, thread-safe)            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Configuration & Domain Layer                               │
│  - Pattern Definitions (patterns.yaml)                      │
│  - Vocabularies & Keywords                                  │
│  - Validation Strategies                                    │
│  - Domain Models                                            │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 Layer Responsibilities

#### **Presentation Layer**

- Streamlit-based web UI for clinical document submission
- Real-time display of redacted documents and entity metadata
- User feedback and status reporting
- **Does not directly implement redaction logic**

#### **Service Layer (RedactionService)**

- Implements **Singleton Pattern** for thread-safe engine access
- Uses **Double-checked Locking** to ensure only one engine instance exists
- Manages engine lifecycle and initialization
- Provides single entry point (`redact_text()`) for all redaction requests
- Handles input validation and error reporting
- Implements secure logging (does not leak PII in logs)

#### **Engine Layer (ContextAwareRedactorEngine)**

- Orchestrates the complete redaction workflow
- Manages the Two-Pass recognition pipeline
- Coordinates between Presidio Analyzer and Anonymizer
- Implements overlap detection and result merging logic
- Maintains cache lifecycle per request

#### **Recognition & NLP Layer**

- **Recognizers**: Specialized entity detectors (provincial health numbers, patient names, contact info, financial data)
- **NLP Engine**: Custom spaCy-based engine with dependency parsing for clinical document understanding
- **Cache**: Request-scoped patient name storage for Pass 2 recall optimization

#### **Configuration & Domain Layer**

- Centralized pattern definitions for all regex-based recognizers
- Vocabulary management (healthcare titles, patient verbs, keywords)
- Provincial health number validation strategies
- Domain models for redaction results

---

## 3. Core Recognition Logic: The Two-Pass Architecture

The system processes every document through a **Two-Pass Recognition Pipeline** to balance precision with recall. This architecture is fundamental to the system's ability to accurately identify patient names while avoiding false positives.

### 3.1 Pass 1: High-Confidence Entity Discovery

**Objective**: Identify entities with strong contextual or grammatical signals.

**Processing Steps**:

1. **Initialize Request Cache**: Create a fresh, request-scoped PatientNameCache using Python's `contextvars` module to ensure thread-safety in concurrent request environments.

2. **Run First-Pass Recognizers**: Execute recognizers that rely on strong detection signals:
   - **PatternRecognizer Chain**: Regex-based detection for provincial health numbers, phone numbers, emails, addresses, dates of birth, postal codes, financial information, and medical record numbers.
   - **CreditCardRecognizer**: Validates credit card patterns with Luhn checksum validation and prefix checks.
   - **PatientNamePatternRecognizer** (Stage 1): Detects patient names explicitly marked with patterns like "Patient Name:" or "Pt Name:".
   - **PatientRoleRecognizer** (Stage 2): Uses dependency parsing to find PERSONs in subject position following patient-specific verbs ("complains", "denies", "reports", "suffers", etc.).
   - **PatientContextRecognizer** (Stage 3): Identifies PERSONs preceded by patient-context keywords ("patient", "member", "Mr.", "Ms.", etc.) within 30-character lookbehind window.

3. **Patient Name Cache Population**: For every PATIENT_NAME entity detected in Pass 1:
   - Extract the matched text from the document
   - Add the full name (e.g., "John Smith") to the cache
   - Split the name and store individual parts (e.g., "John", "Smith") with minimum 3-character threshold and stop-word filtering
   - Mark cache as "initialized" once data is added

4. **Output**: List of high-confidence RecognizerResult objects + populated cache with patient names and name parts.

**Design Rationale**: These recognizers employ multiple independent detection signals (regex, grammatical role, contextual keywords), making false positives unlikely. Results from Pass 1 are considered "ground truth" for the entity boundaries.

### 3.2 Pass 2: Recall-Boosting Ad-Hoc Recognition

**Objective**: Catch patient name occurrences that lack strong contextual signals (e.g., "John was sleeping" where "John" appears alone).

**Processing Steps**:

1. **Cache-Dependent Recognition**: Only executes if cache was populated (i.e., at least one patient name found in Pass 1).

2. **Two-Tier Matching Strategy**:
   - **Full Name Matching** (Iteration): For each full name in cache, search the document for all occurrences (case-insensitive). Score: 0.95.
   - **Name Part Matching** (Optimized Regex): Compile a single high-performance regex pattern containing all name parts: `\b(?:John|Smith|Jane)\b`. This one-pass regex outperforms iterative matching. Score: 0.85.

3. **Healthcare Provider Safety Check**: For each matched name part, examine the 15-character lookbehind context for healthcare titles. If a provider title is found (e.g., "Dr.", "Cardiologist"), discard the match to prevent accidental redaction of provider names sharing parts with patient names.

4. **Overlap Prevention**: Maintain set of character indices covered by Pass 1 results. Only add Pass 2 results if they don't overlap with existing high-confidence entities.

5. **Output**: Additional RecognizerResult objects for name parts missed in Pass 1, with lower confidence scores but higher recall.

**Design Rationale**: Pass 2 trades confidence for recall. By using the cache populated in Pass 1 as a "training set," we can find additional instances. Overlap prevention ensures Pass 1 high-confidence results always take priority.

### 3.3 Result Merging & De-duplication

**Processing Steps**:

1. **Combine Results**: Merge Pass 1 and Pass 2 results into a single list.

2. **Overlap Detection**: Identify any overlapping character ranges between results.

3. **Conflict Resolution**: If overlaps exist, keep Pass 1 result (higher confidence) and discard the Pass 2 result. Log the discard event for debugging.

4. **Pass to Anonymizer**: Send the de-duplicated result list to Presidio's AnonymizerEngine with operator configurations specifying placeholder text for each entity type.

5. **Output**: RedactionResult containing redacted text and metadata about detected entities.

---

## 4. Patient vs. Provider Distinction: Multi-Layer Defense

The system's ability to accurately distinguish patient names from healthcare provider names is critical to clinical document integrity. This is achieved through a **multi-layer detection and exclusion strategy** implemented across multiple components.

### 4.1 Layer 1: Healthcare Provider Tagging (Pre-Detection Exclusion)

**Location**: CanadianClinicalNlpEngine's `role_extractor` pipeline component.

**Mechanism**:

1. **Title Extraction**: Load a predefined vocabulary of healthcare titles from patterns.yaml (e.g., "Dr", "Dr.", "Doctor", "Physician", "Surgeon", "Cardiologist", "Nurse", "Therapist", "Consultant", "Prof", "Professor").

2. **Token Tagging**: For every PERSON entity identified by spaCy's NER:
   - Check if the immediately preceding token (entity.start - 1) is a known healthcare title (case-insensitive match).
   - If match found, set `is_healthcare_provider = True` custom extension on all tokens within the entity.

3. **Effect**: All downstream recognizers are configured to skip any entity with this tag, preventing accidental redaction.

**Example**:

```
Text: "Dr. Smith examined the patient John."
Result: Dr. Smith → is_healthcare_provider=True (SKIPPED)
         John     → is_healthcare_provider=False (PROCESSED)
```

### 4.2 Layer 2: Syntactic Role Analysis (Dependency Parsing)

**Location**: CanadianClinicalNlpEngine's `role_extractor` component.

**Mechanism**:

1. **Dependency Matcher Setup**: Initialize spaCy's DependencyMatcher with two patterns:
   - **Active Voice**: PERSON in subject position (DEP=nsubj) following an active patient verb ("complains", "denies", "reports", "suffer", "experience", "feel", "undergo", "receive").
   - **Passive Voice**: PERSON in subject position (DEP=nsubjpass) following a passive patient verb ("see", "admit", "examine", "treat", "diagnose", "assess", "refer", "discharge", "hospitalize").

2. **Pattern Matching**: Execute dependency matcher against parsed document to find all such grammatical patterns.

3. **Token Marking**: For matches where subject_token is not already marked as healthcare_provider:
   - Set `role = "PATIENT"` on the subject token
   - Propagate the PATIENT role to the entire PERSON entity if all tokens are safe (no tokens marked as healthcare_provider)

4. **Effect**: Enables PatientRoleRecognizer to detect patients based on how they interact grammatically with the text (being the subject of patient-specific verbs indicates patient status).

**Example**:

```
Text: "The patient John complained of chest pain."
Parsed: complained(VERB) → John(nsubj) + John(PERSON)
Result: John._.role = "PATIENT" (flagged for redaction)

Text: "Cardiologist Dr. Smith complained about staffing."
Parsed: complained(VERB) → Smith(nsubj) + Smith(PERSON, preceded by "Dr.")
Result: Smith._.is_healthcare_provider = True, Smith._.role remains None (SKIPPED)
```

### 4.3 Layer 3: Contextual Keyword Analysis

**Location**: PatientContextRecognizer recognizer.

**Mechanism**:

1. **Keyword Dictionary**: Load patient-context keywords from vocabulary (e.g., "patient", "member", "Mr.", "Ms.", "Mrs.", "Miss").

2. **Window Analysis**: For each PERSON entity identified by spaCy NER:
   - Skip if already marked as healthcare_provider
   - Extract 30-character lookbehind context (text[start_char-30:start_char])
   - Convert to lowercase and search for any patient keyword

3. **Scoring**: If any keyword found, assign score 0.90 (high confidence) and flag as PATIENT_NAME.

4. **Effect**: Catches constructions like "The patient John had..." or "Member Ms. Smith reported..." where the entity's role is explicitly stated.

**Example**:

```
Text: "The patient John experienced shortness of breath."
Context: "The patient "
Result: John → score=0.90 (PATIENT_NAME)

Text: "Member Ms. Smith received care at the clinic."
Context: "Member Ms. "
Result: Smith → score=0.90 (PATIENT_NAME)
```

### 4.4 Layer 4: Pass 2 Provider Safety Check

**Location**: PatientNameRecognizer recognizer (Stage 4, Pass 2).

**Mechanism**:

1. **Preventive Filtering**: During Pass 2 name-part matching, before adding a name-part match result:
   - Extract 15-character lookbehind context
   - Search for healthcare titles using regex word boundaries
   - If title found, discard the match

2. **Effect**: Prevents false positives where a provider shares a name part with a patient (e.g., "Dr. Johnson" should not be redacted even if "Johnson" was identified as a patient part).

**Example**:

```
Text: "Dr. Smith treated patient Smith."
Pass 1: Patient Smith → cache.add_full_name("Smith")
Pass 2: Searching for "Smith"
        - Match 1: "Dr. Smith" → Context has "Dr." → SKIP
        - Match 2: "patient Smith" → No title in context → REDACT

Result: "Dr. Smith treated patient <PATIENT_NAME>."
```

---

## 5. Recognizer Architecture

The system employs a **Recognizer Registry Pattern** with specialized recognizers for different PII categories. Each recognizer is independently configurable and testable.

### 5.1 Recognizer Types

**Pattern-Based Recognizers**:

- ProvincialHealthRecognizer: Detects provincial health numbers (ON, BC, QC, AB, SK, MB, NS, NB, NL, PE, NT, NU, YT) with province-specific validation (Luhn checksum for most provinces).
- CreditCardRecognizer: Matches credit card patterns (13-19 digits) and validates with Luhn checksum and valid issuer prefix (4, 5, 6, 3).
- PatternRecognizer instances: Generic regex-based recognizers for phone, email, address, date of birth, postal code, bank account, transaction ID, bank name, and medical record number.

**Entity-Based Recognizers (Custom NLP)**:

- PatientNamePatternRecognizer: Detects explicit patterns like "Patient Name: " or "Pt Name: ".
- PatientRoleRecognizer: Uses dependency parsing results to identify grammatical patients.
- PatientContextRecognizer: Uses contextual keywords to identify patients.
- PatientNameRecognizer: (Pass 2 only) Matches cached patient names and name parts.

### 5.2 Recognizer Initialization & Configuration

All recognizers are dynamically instantiated based on pattern definitions in `patterns.yaml`:

1. **PatternLoader Singleton**: Loads and caches patterns.yaml once at application startup.
2. **Recognizer Registry**: Presidio's RecognizerRegistry maintains all active recognizers.
3. **Dynamic Loading**: Recognizers for missing patterns are skipped with warning logs.

### 5.3 Recognizer Execution Order (Pass 1)

Recognizers execute in the order returned by Presidio's AnalyzerEngine. All Pass 1 recognizers contribute to a single analysis pass (no explicit ordering enforced). However, the patient-name recognizers are designed with an implicit dependency: PatientNamePatternRecognizer, PatientRoleRecognizer, and PatientContextRecognizer all contribute independent signals, with PatientNameRecognizer (Pass 2) intentionally excluded from Pass 1.

---

## 6. Natural Language Processing: CanadianClinicalNlpEngine

The system extends Presidio's standard spaCy integration with a custom NLP engine that performs clinical-specific dependency parsing and token tagging.

### 6.1 Engine Design

**Inheritance**: Extends Presidio's SpacyNlpEngine.

**Model**: Uses spaCy's `en_core_web_lg` model (large, trained on English web text) for robust NER and dependency parsing.

**Custom Components**: Adds a `role_extractor` pipeline component (registered as spaCy component) that runs after standard spaCy components.

### 6.2 Custom Token Extensions

Two custom extensions are registered on spaCy's Token class:

1. **`token._.role`** (default=None):
   - Set to "PATIENT" by dependency matcher if token is subject of patient-specific verb
   - Used by PatientRoleRecognizer to identify entities

2. **`token._.is_healthcare_provider`** (default=False):
   - Set to True if token is part of a PERSON entity preceded by healthcare title
   - Checked by all patient recognizers to skip provider names

### 6.3 Role Extractor Component (Pipeline Step)

The role_extractor component performs three sequential operations on each document:

**Step 1: Healthcare Provider Identification**:

- Iterate through spaCy NER entities
- For PERSON entities, check if previous token is healthcare title
- Mark all tokens in entity with `is_healthcare_provider = True`

**Step 2: Dependency Pattern Matching**:

- Create DependencyMatcher with two patterns (active/passive)
- Execute against document dependency tree
- Collect all matches (token pairs: verb + subject)

**Step 3: Patient Role Tagging**:

- For each matched subject token:
  - Skip if already marked as healthcare_provider
  - Set `token._.role = "PATIENT"`
  - If subject token is part of a PERSON entity with no provider tokens, mark entire entity

---

## 7. Caching Architecture: Request-Scoped Patient Name Storage

The system uses a sophisticated caching strategy to store identified patient names for Pass 2 ad-hoc recognition while maintaining thread-safety in concurrent environments.

### 7.1 Cache Design

**Technology**: Python's `contextvars` module provides request-scoped storage.

**Scope**: Each request gets an isolated cache instance; concurrent requests do not share cache data.

**Lifecycle**:

- Created at the start of ContextAwareRedactorEngine.process()
- Populated during Pass 1
- Consumed during Pass 2
- Reset at the start of the next request

### 7.2 PatientNameCache Structure

**Data Members**:

- `full_names` (Set[str]): Complete patient names identified in Pass 1 (e.g., "John Smith")
- `name_parts` (Set[str]): Individual name components (e.g., "John", "Smith") with 3+ character minimum and stop-word filtering
- `stop_words` (Set[str]): Common words excluded from name parts (e.g., "the", "of", "and", "in", "to")
- `initialized` (bool): Flag indicating cache has been populated (used to conditionally run Pass 2)

### 7.3 Cache Operations

**add_full_name(name: str)**:

- Validate input is not empty and not a stop word
- Add lowercase version to full_names
- Split into parts, filter (length > 2, not stop word), add to name_parts
- Set initialized = True

**is_patient_name(text: str) -> bool**:

- Check if text (lowercase) exists in full_names
- Check if text (lowercase) exists in name_parts
- Return True if either match

**reset()**:

- Clear all data members
- Called at start of each request to ensure clean state

### 7.4 Thread-Safety Mechanism

**ContextVar Storage**:

- Cache instance stored in module-level ContextVar: `_patient_cache_var`
- ContextVar automatically isolates data per execution context (request)
- Each async request or thread gets its own ContextVar value
- No explicit locks needed; isolation is automatic

**Design Advantage**: Allows the same application code to serve multiple concurrent requests without data contamination. Critical for cloud deployments (Azure Web Apps) where multiple requests execute simultaneously.

---

## 8. Configuration Management: patterns.yaml

All patterns, vocabularies, and keywords are centralized in a single YAML configuration file loaded at application startup.

### 8.1 Configuration Structure

**Top-Level Sections**:

1. **vocabulary**: Domain primitives (titles, verbs, keywords)
   - `healthcare_titles`: Provider titles (Dr, Nurse, Cardiologist, etc.)
   - `patient_verbs_active`: Patient-active verbs (complain, deny, report, suffer, etc.)
   - `patient_verbs_passive`: Patient-passive verbs (see, admit, examine, treat, diagnose, etc.)
   - `patient_context_keywords`: Keywords indicating patient context (patient, member, Mr., Ms., etc.)
   - `credit_card_context`: Keywords for credit card context (card, credit, visa, payment, etc.)
   - `stop_words`: Common words filtered from name parts (of, the, and, in, to, etc.)

2. **patterns**: Regex pattern definitions for entity detection
   - Each entity type (e.g., ON_HCN, PHONE, EMAIL) has array of patterns
   - Pattern structure: `{ name, regex, score }`
   - Score represents confidence (0.0-1.0)

3. **provinces**: Provincial configuration
   - Per-province keywords for context validation

### 8.2 PatternLoader Singleton

**Responsibilities**:

- Load patterns.yaml once at startup
- Cache configuration in memory for application lifetime
- Provide accessor methods for patterns, vocabularies, provinces
- Validate configuration on load (ensure required sections exist)

**Thread-Safety**: Configuration is immutable after load; concurrent reads are safe.

---

## 9. Entity Types & Definitions

The system defines a comprehensive set of supported entity types, organized by category:

**Healthcare Provider Information** (Never Redacted):

- HEALTHCARE_PROVIDER_NAME: Names of medical professionals

**Patient Information** (Always Redacted):

- PATIENT_NAME: Patient's full or partial name

**Contact Information** (Always Redacted):

- PHONE: Phone numbers (domestic and international)
- EMAIL: Email addresses
- ADDRESS: Postal addresses
- POSTAL_CODE: Postal codes

**Identity Documents** (Always Redacted):

- PROVINCIAL_HEALTH_NUMBER: Provincial health numbers (all provinces/territories)
  - ON_HCN, BC_PHN, QC_RAMQ, AB_PHN, SK_HSN, MB_PHIN, NS_HCN, NB_MEDICARE, NL_MCP, PE_HEALTH, NT_HSN, NU_HEALTH, YT_YHCIP
- MEDICAL_RECORD_NUMBER: Hospital/clinic medical record identifiers
- DOB: Date of birth
- PROVINCE: Province name (sensitive in context of health records)

**Financial Information** (Always Redacted):

- CREDIT_CARD: Credit card numbers (Luhn-validated)
- BANK_ACCOUNT: Bank account numbers
- BANK_NAME: Financial institution names
- TRANSACTION_ID: Transaction identifiers

---

## 10. Anonymization Strategy

Once entities are detected, the Presidio AnonymizerEngine replaces them with standardized placeholders.

### 10.1 Placeholder Convention

Each entity type maps to a placeholder:

- PATIENT_NAME → `<PATIENT_NAME>`
- PHONE → `<PHONE>`
- EMAIL → `<EMAIL>`
- ADDRESS → `<ADDRESS>`
- ON_HCN → `<ON_HCN>` (province-specific)
- CREDIT_CARD → `<CREDIT_CARD>`
- DATE → `<DATE>`
- And so on...

### 10.2 Anonymization Process

1. Generate OperatorConfig for each entity type, specifying "replace" operator with placeholder text
2. Pass combined results list and operators to AnonymizerEngine
3. Engine performs in-place replacement at character positions specified by results
4. Overlap protection (enforced in merge step) ensures no double-redaction

---

## 11. Security & Privacy Considerations

The system implements multiple security measures to protect PII during processing and logging:

### 11.1 Logging Strategy

**No PII in Logs**:

- Exception messages are NOT included in structured logs (may contain PII)
- Only non-sensitive metadata logged: text_length, entity_count, threshold, cache_size
- Error messages returned to users are generic ("An internal error occurred") without implementation details

**Secure Logging Pattern**:

- Log stacktrace with `exc_info=True` for debugging (not visible to end users)
- Include only error type, not error message content
- Extra metadata contains only counts and configuration, never actual text

### 11.2 Request-Scoped Cache Isolation

- ContextVar-based caching ensures each request has isolated cache
- No cross-request data leakage even in concurrent environments
- Cache reset at start of each request

### 11.3 Input Validation

- Empty text rejected at service layer
- Type checking enforced (must be string)
- Entity list validation (cannot be empty)

---

## 12. Request Flow: End-to-End Processing

A complete end-to-end flow of a redaction request:

1. **User Input**: Streamlit UI receives clinical document text
2. **Service Entry**: `redact_text()` validates input, retrieves singleton engine
3. **Engine Processing**:
   a. Create/reset request-scoped PatientNameCache
   b. Execute Pass 1 (all standard recognizers)
   c. Populate cache with Pass 1 patient names
   d. Execute Pass 2 (PatientNameRecognizer using cache)
   e. Merge results, remove overlaps (Pass 1 takes precedence)
   f. Anonymize with placeholders
4. **Result Construction**: Create RedactionResult with redacted text and metadata
5. **Response**: Return to Streamlit UI for display

**Error Handling**: Any exception caught at service layer, logged securely, generic error returned to user.

---

## 13. Performance Considerations & Optimizations

### 13.1 Pattern Compilation

- ProvincialHealthRecognizer and PatientNameRecognizer compile regex patterns once at initialization
- PatientNameRecognizer builds optimized single-pass regex for name-part matching (not iterative)
- Sorted name parts (descending length) to match longer names before substrings

### 13.2 Caching

- Patterns loaded once from patterns.yaml at startup
- Configuration cached in PatternLoader singleton
- Request-scoped patient name cache populated during Pass 1, used in Pass 2 (2x speedup vs. single-pass with lower recall)

### 13.3 Overlap Detection

- Uses set-based character index tracking for O(N) performance
- Merge operation efficient even for large documents

---

## 14. Extensibility & Future Development

### 14.1 Adding New Entity Types

1. Define entity type constant in EntityType definitions
2. Add patterns to patterns.yaml (patterns section)
3. Create PatternRecognizer instance for entity type in create_all_recognizers()
4. System automatically includes new recognizer

### 14.2 Adding New Healthcare Titles

1. Edit patterns.yaml vocabulary section (healthcare_titles)
2. System automatically uses new titles in provider tagging
3. No code changes required

### 14.3 Adding New Patient Context Keywords

1. Edit patterns.yaml vocabulary section (patient_context_keywords)
2. PatientContextRecognizer automatically uses new keywords
3. No code changes required

### 14.4 Enhancing Patient Verb Patterns

1. Add new verbs to patterns.yaml vocabulary (patient_verbs_active or patient_verbs_passive)
2. DependencyMatcher in role_extractor automatically includes new patterns
3. No code changes required

### 14.5 Adding New Validation Strategies

1. Extend ValidatorStrategy base class
2. Implement province-specific validate() method with Luhn or custom checksum logic
3. Add to get_validator() factory in validators.py
4. Recognizer automatically uses new strategy

---

## 15. Architectural Principles & Design Patterns

### 15.1 Design Patterns Used

1. **Singleton Pattern**: RedactionService, PatternLoader, PatientNameCache (via ContextVar)
2. **Registry Pattern**: Presidio's RecognizerRegistry manages all recognizers
3. **Factory Pattern**: create_all_recognizers(), get_validator()
4. **Strategy Pattern**: ValidatorStrategy for province-specific validation
5. **Pipeline Pattern**: Role extractor as spaCy pipeline component
6. **Dependency Injection**: PatientNameRecognizer receives cache via constructor

### 15.2 Architectural Principles

1. **Separation of Concerns**: Each layer has focused responsibility (NLP, recognition, anonymization, config)
2. **Single Responsibility**: Each recognizer detects one category of entities
3. **Configuration-Driven**: Patterns and vocabularies external to code (patterns.yaml)
4. **Fail-Safe Defaults**: Missing patterns logged but don't crash application
5. **Layered Defense**: Multiple independent signals for patient vs. provider distinction prevent single-point failure
6. **Thread-Safety First**: ContextVar-based caching for concurrent request safety
7. **Testability**: Each component independently testable; minimal coupling between layers

---

## 16. Integration Points & APIs

### 16.1 Main Service API

**Function**: `redact_text(text: str) -> RedactionResult`

**Input**:

- `text`: Clinical document as string

**Output**:

- `RedactionResult` with fields:
  - `original_text`: Input text
  - `redacted_text`: Text with entities replaced by placeholders
  - `entities`: List of RedactedEntity objects (type, position, score, rule_name)
  - `metadata`: Dict with count, engine name, entity_types found

**Usage**: Called directly from Streamlit UI; handles engine lifecycle and error management

### 16.2 Engine Configuration

**Config Class**: Located in redaction/service/config.py

**Key Settings**:

- `SPACY_MODEL`: Model name (default: "en_core_web_lg")
- `CONFIDENCE_THRESHOLD`: Minimum confidence score (default: typically 0.5)
- `DEFAULT_ENTITIES`: List of entity types to detect (includes all active entities)

---

## 17. Limitations & Known Constraints

1. **Language**: English only; non-English clinical documents will have reduced accuracy
2. **Ambiguous Names**: Common names (e.g., "John Smith") may match unrelated Johns/Smiths; mitigation is context validation
3. **Provider Name Sharing**: If provider and patient share exact name, Pass 2 depends on healthcare title in context; unusual edge case
4. **Typos & Abbreviations**: Misspelled patient names or nicknames may not be caught; mitigation is context-based recognizers
5. **Custom Abbreviations**: Institution-specific abbreviations not in standard patterns may not be recognized

---

## 18. Monitoring & Debugging

### 18.1 Structured Logging

- Engine logs redaction completion with entity_count, text_length, cache_size
- Recognizers log skipped patterns and missing configuration
- Errors logged with type, not message content, for security

### 18.2 Debugging Information

RedactionResult metadata includes:

- `count`: Total entities found
- `engine`: Engine type ("CanadianClinicalNlpEngine")
- `entity_types`: List of entity types detected

Each entity includes `rule_name`: name of recognizer that detected it (e.g., "PatientNamePattern_Recognizer", "PatientRoleRecognizer")

---

## 19. Conclusion

The Context Aware Redactor implements a sophisticated **multi-layer, multi-pass architecture** designed to accurately redact patient information while preserving healthcare provider names and institutional information. The system achieves this through:

- **Two-Pass Recognition Pipeline**: High-confidence Pass 1 + Recall-boosting Pass 2
- **Multi-Layer Patient vs. Provider Distinction**: Provider tagging, dependency parsing, contextual keywords, safety checks
- **Request-Scoped Caching**: Thread-safe ContextVar-based isolation for concurrent requests
- **Configuration-Driven Design**: All patterns and vocabularies external to code
- **Security-First Logging**: No PII leaked in logs or error messages

Future development must respect the established layer boundaries, configuration-driven patterns, and multi-layer distinction logic to maintain system integrity and prevent breaking changes.
