# main.py

"""Streamlit web UI for the Canadian PII redaction system.

Provides a simple interface to submit clinical text and receive a
redacted version highlighting detected PII/PHI entities.
"""

import streamlit as st
import logging
from redaction.service.pipeline import redact_text

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def main():
    """Run the Streamlit application UI.

    This function configures the Streamlit page, accepts input text from
    the user, invokes the redaction pipeline, and displays the redacted
    output along with basic status information.
    """
    st.set_page_config(
        layout="wide", page_title="Canadian PII Redaction System", page_icon="🛡️"
    )

    st.title("Canadian PII Redaction System")
    st.markdown(
        "Secure redaction of Personal Health Information (PHI) and Personally Identifiable Information (PII) from Canadian healthcare documents."
    )
    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Input Clinical Text")
        text_input = st.text_area(
            "Source Document",
            height=400,
            placeholder="Paste clinical document text here...",
        )

    with col2:
        st.subheader("Redacted Output")

        if st.button("Redact PII", type="primary"):
            if not text_input or not text_input.strip():
                st.warning("Please enter text to process.")
                logger.warning("Redaction attempted with empty input")

            else:
                try:
                    with st.spinner("Analyzing document..."):
                        logger.info(f"Processing document of length: {len(text_input)}")
                        result = redact_text(text_input)

                    if "error" in result.metadata:
                        st.error(f"Redaction failed: {result.metadata['error']}")
                        logger.error(
                            "Redaction returned error status",
                            extra={"status": "failed", "text_length": len(text_input)},
                        )
                    else:
                        st.text_area(
                            "Redacted Document", value=result.redacted_text, height=400
                        )

                        st.success(
                            f"Redaction complete. Found {len(result.entities)} entities."
                        )

                        logger.info(
                            f"Redaction successful: {len(result.entities)} entities found",
                            extra={"text_length": len(text_input)},
                        )

                except Exception:
                    st.error("An unexpected error occurred during redaction.")
                    logger.error(
                        "Unexpected error in main application loop",
                        exc_info=True,
                        extra={"text_length": len(text_input) if text_input else 0},
                    )

    with st.sidebar:
        st.header("About")
        st.markdown("""
        This system redacts sensitive information from Canadian healthcare documents including:
        
        - **Provincial Health Numbers** (All provinces/territories)
        - **Patient Names** (Context-aware detection)
        - **Contact Information** (Phone, email, addresses)
        - **Financial Data** (Bank accounts, credit cards)
        - **Medical Record Numbers**
        - **Dates of Birth**
        
        The system uses advanced NLP to distinguish between patient names and healthcare provider names.
        """)

        st.header("Status")
        st.success("System Ready")


if __name__ == "__main__":
    main()
