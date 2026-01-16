# redaction/core/definitions.py

"""Entity type constants for PII/PHI detection in Canadian healthcare documents."""


class EntityType:
    """Constants representing detectable PII/PHI entity types."""

    # Provincial Health Numbers
    ON_HCN = "ON_HEALTH_CARD"
    BC_PHN = "BC_PHN"
    QC_RAMQ = "QC_RAMQ"
    AB_PHN = "AB_PHN"
    SK_HSN = "SK_HSN"
    MB_PHIN = "MB_PHIN"
    NS_HCN = "NS_HEALTH_CARD"
    NB_MEDICARE = "NB_MEDICARE"
    NL_MCP = "NL_MCP"
    PE_HEALTH = "PE_HEALTH_NUMBER"
    NT_HSN = "NT_HSN"
    NU_HEALTH = "NU_HEALTH_NUMBER"
    YT_YHCIP = "YT_YHCIP"

    # General PII/PHI
    PATIENT_NAME = "PATIENT_NAME"
    DOB = "DATE_OF_BIRTH"
    PHONE = "PHONE_NUMBER"
    EMAIL = "EMAIL_ADDRESS"
    ADDRESS = "STREET_ADDRESS"
    POSTAL_CODE = "CA_POSTAL_CODE"
    PROVINCE = "CA_PROVINCE"
    BANK_ACCT = "CA_BANK_ACCT"
    CREDIT_CARD = "CREDIT_CARD"
    TX_ID = "TRANSACTION_ID"
    BANK_NAME = "FINANCIAL_INSTITUTION"
    MRN = "MEDICAL_RECORD_NUMBER"
