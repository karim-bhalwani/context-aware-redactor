# redaction/engine/spacy_driver.py

"""Custom SpaCy NLP engine with clinical dependency parsing."""

import logging
import spacy
from spacy.matcher import DependencyMatcher
from spacy.language import Language
from spacy.tokens import Token
from presidio_analyzer.nlp_engine import SpacyNlpEngine

from redaction.core.loader import PatternLoader

logger = logging.getLogger(__name__)


class CanadianClinicalNlpEngine(SpacyNlpEngine):
    """SpaCy NLP engine extended with clinical dependency parsing."""

    def __init__(self, models_config):
        models = (
            models_config.get("models")
            if isinstance(models_config, dict)
            else models_config
        )

        if not models:
            # Disable 'textcat' (classification) and 'senter' (sentence tokenizer)
            # as 'parser' handles sentence boundaries sufficiently for this use case.
            models = [
                {
                    "lang_code": "en",
                    "model_name": "en_core_web_lg",
                    "exclude": ["textcat", "senter"],
                }
            ]

        logger.info(f"Initializing SpacyNlpEngine with models: {models}")

        super().__init__(models=models)

        # Ensure the model is loaded
        if not self.nlp or "en" not in self.nlp:
            logger.warning("Model 'en' not loaded by parent. Attempting manual load.")
            try:
                model_conf = models[0]
                model_name = model_conf["model_name"]
                exclude = model_conf.get("exclude", [])

                self.nlp = {"en": spacy.load(model_name, exclude=exclude)}
                logger.info(f"Loaded spaCy model '{model_name}' excluding {exclude}")
            except Exception as e:
                logger.error(f"Failed to load spaCy model: {e}")
                raise ValueError(f"Could not load spaCy model '{model_name}'")

        nlp = self.nlp["en"]

        # Register custom extensions
        if not Token.has_extension("role"):
            Token.set_extension("role", default=None)

        if not Token.has_extension("is_healthcare_provider"):
            Token.set_extension("is_healthcare_provider", default=False)

        # Add component to pipeline
        if "role_extractor" not in nlp.pipe_names:
            nlp.add_pipe("role_extractor", last=True)
            logger.info("Added 'role_extractor' to spaCy pipeline")

    @staticmethod
    @Language.component("role_extractor")
    def role_extractor_component(doc):
        """SpaCy pipeline component for clinical role extraction."""
        loader = PatternLoader.get_instance()

        # 1. Identify Healthcare Providers
        healthcare_titles = set(loader.get_vocabulary("healthcare_titles"))

        for ent in doc.ents:
            if ent.label_ == "PERSON" and ent.start > 0:
                prev_token = doc[ent.start - 1]
                if prev_token.text.lower() in healthcare_titles:
                    for token in ent:
                        token._.is_healthcare_provider = True

        # 2. Dependency Matching for Patient Role
        matcher = DependencyMatcher(doc.vocab)

        verbs_active = loader.get_vocabulary("patient_verbs_active")
        verbs_passive = loader.get_vocabulary("patient_verbs_passive")

        patient_active_pattern = [
            {
                "RIGHT_ID": "verb",
                "RIGHT_ATTRS": {"LEMMA": {"IN": verbs_active}},
            },
            {
                "LEFT_ID": "verb",
                "REL_OP": ">",
                "RIGHT_ID": "subject",
                "RIGHT_ATTRS": {"DEP": "nsubj", "ENT_TYPE": "PERSON"},
            },
        ]

        patient_passive_pattern = [
            {
                "RIGHT_ID": "verb",
                "RIGHT_ATTRS": {"LEMMA": {"IN": verbs_passive}},
            },
            {
                "LEFT_ID": "verb",
                "REL_OP": ">",
                "RIGHT_ID": "subject",
                "RIGHT_ATTRS": {"DEP": "nsubjpass", "ENT_TYPE": "PERSON"},
            },
        ]

        matcher.add("PATIENT_ROLE", [patient_active_pattern, patient_passive_pattern])
        matches = matcher(doc)

        # 3. Tag Patient Names
        for _, token_ids in matches:
            subject_token = doc[token_ids[1]]

            if subject_token._.is_healthcare_provider:
                continue

            subject_token._.role = "PATIENT"

            if subject_token.ent_type_ == "PERSON":
                for ent in doc.ents:
                    if subject_token.i >= ent.start and subject_token.i < ent.end:
                        if not any(t._.is_healthcare_provider for t in ent):
                            for token in ent:
                                token._.role = "PATIENT"
                        break

        return doc
