# """
# Enterprise PII Detection & Masking Service mimicking Microsoft Presidio.
# Python port of src/services/presidio.ts
# """
# import re
# import json
# import logging
# from dataclasses import dataclass, asdict
# from typing import Dict, List, Optional

# from google import genai
# from google.genai import types

# logger = logging.getLogger(__name__)

# GEMINI_MODEL = "gemini-3.5-flash"


# @dataclass
# class PiiMapping:
#     original: str
#     masked: str
#     type: str


# class PresidioService:
#     """Secure bi-directional PII mapping store: key is masked placeholder."""

#     # key: placeholder -> PiiMapping
#     _mapping_store: Dict[str, PiiMapping] = {}
#     _counter_map: Dict[str, int] = {}

#     _patterns = {
#         "EMAIL": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
#         "PHONE": re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"),
#         "CREDIT_CARD": re.compile(
#             r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|"
#             r"3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}|"
#             r"(?:2131|1800|35\d{3})\d{11})\b"
#         ),
#         "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
#         "IP_ADDRESS": re.compile(
#             r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
#             r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
#         ),
#     }

#     # -------------------------------------------------------------
#     # Placeholder management
#     # -------------------------------------------------------------
#     @classmethod
#     def _get_placeholder(cls, entity_type: str, original: str) -> str:
#         # Reuse existing placeholder if this original value was already masked
#         for placeholder, mapping in cls._mapping_store.items():
#             if mapping.original == original and mapping.type == entity_type:
#                 return placeholder

#         current_count = cls._counter_map.get(entity_type, 0)
#         placeholder = f"<{entity_type}_{current_count}>"
#         cls._counter_map[entity_type] = current_count + 1

#         cls._mapping_store[placeholder] = PiiMapping(
#             original=original, masked=placeholder, type=entity_type
#         )
#         return placeholder

#     # -------------------------------------------------------------
#     # Regex based masking
#     # -------------------------------------------------------------
#     @classmethod
#     def mask_regex_pii(cls, text: str) -> str:
#         masked = text

#         masked = cls._patterns["SSN"].sub(
#             lambda m: cls._get_placeholder("SSN", m.group(0)), masked
#         )
#         masked = cls._patterns["CREDIT_CARD"].sub(
#             lambda m: cls._get_placeholder("CREDIT_CARD", m.group(0)), masked
#         )
#         masked = cls._patterns["EMAIL"].sub(
#             lambda m: cls._get_placeholder("EMAIL", m.group(0)), masked
#         )
#         masked = cls._patterns["PHONE"].sub(
#             lambda m: cls._get_placeholder("PHONE", m.group(0)), masked
#         )
#         masked = cls._patterns["IP_ADDRESS"].sub(
#             lambda m: cls._get_placeholder("IP", m.group(0)), masked
#         )

#         return masked

#     # -------------------------------------------------------------
#     # Advanced LLM based NER masking (Names, Organizations, Locations)
#     # -------------------------------------------------------------
#     @classmethod
#     async def mask_advanced_pii(cls, text: str, api_key: Optional[str] = None) -> str:
#         if not api_key or not text or not text.strip():
#             return cls.mask_regex_pii(text)

#         try:
#             client = genai.Client(api_key=api_key)

#             prompt = f"""You are the NER (Named Entity Recognition) engine of Microsoft Presidio PII Protection system.
# Analyze the following text and extract sensitive entities to mask.
# Extract only:
# - PERSON (Full names or single names of people, e.g., "John Doe")
# - ORGANIZATION (Company names, institutions, e.g., "Acme Corp")
# - LOCATION (Addresses, cities, specific places, e.g., "123 Main St", "London")

# Do NOT extract generic words or non-PII terms.

# Text to analyze:
# \"\"\"
# {text}
# \"\"\"

# Return your findings in valid JSON format only, matching this structure:
# {{
#   "entities": [
#     {{ "text": "entity text to mask", "type": "PERSON" | "ORGANIZATION" | "LOCATION" }}
#   ]
# }}"""

#             response = client.models.generate_content(
#                 model=GEMINI_MODEL,
#                 contents=prompt,
#                 config=types.GenerateContentConfig(
#                     response_mime_type="application/json",
#                     temperature=0.1,
#                 ),
#             )

#             response_text = response.text or "{}"
#             data = json.loads(response_text)

#             masked = cls.mask_regex_pii(text)

#             entities = data.get("entities") or []
#             # Sort entities by length descending to prevent substring masking conflicts
#             sorted_entities = sorted(
#                 entities, key=lambda e: len(e.get("text", "")), reverse=True
#             )

#             for entity in sorted_entities:
#                 entity_text = entity.get("text", "")
#                 if not entity_text or len(entity_text.strip()) < 2:
#                     continue

#                 escaped = re.escape(entity_text)
#                 pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
#                 entity_type = entity.get("type", "UNKNOWN")

#                 masked = pattern.sub(
#                     lambda m: cls._get_placeholder(entity_type, m.group(0)), masked
#                 )

#             return masked
#         except Exception as error:
#             logger.error("Presidio Advanced NER error: %s", error)
#             # Fallback to regex-only masking if LLM NER fails
#             return cls.mask_regex_pii(text)

#     # -------------------------------------------------------------
#     # Re-identification
#     # -------------------------------------------------------------
#     @classmethod
#     def demask_text(cls, text: str) -> str:
#         if not text:
#             return text
#         demasked = text

#         placeholders = sorted(cls._mapping_store.keys(), key=len, reverse=True)

#         for placeholder in placeholders:
#             mapping = cls._mapping_store.get(placeholder)
#             if mapping:
#                 demasked = demasked.replace(placeholder, mapping.original)

#         return demasked

#     # -------------------------------------------------------------
#     # Accessors
#     # -------------------------------------------------------------
#     @classmethod
#     def get_mappings(cls) -> List[dict]:
#         return [asdict(m) for m in cls._mapping_store.values()]

#     @classmethod
#     def clear_mappings(cls) -> None:
#         cls._mapping_store.clear()
#         cls._counter_map.clear()

#########################################################################################################
#########################################################################################################
#########################################################################################################

# """
# Enterprise PII Detection & Masking Service.
# Hybrid approach:
# - Presidio SDK regex recognizers: EMAIL, PHONE, CREDIT_CARD, SSN, IP_ADDRESS
# - Gemini LLM NER: PERSON, ORGANIZATION, LOCATION
# No spaCy language model required.
# """
# import json
# import logging
# import re
# from dataclasses import dataclass, asdict
# from pathlib import Path
# from typing import Dict, List, Optional, Set, Tuple

# from google import genai
# from google.genai import types

# # Presidio standalone regex recognizers — no spaCy model needed
# from presidio_analyzer.predefined_recognizers import (
#     EmailRecognizer,
#     PhoneRecognizer,
#     CreditCardRecognizer,
#     UsSsnRecognizer,
#     IpRecognizer,
# )

# logger = logging.getLogger(__name__)

# GEMINI_MODEL = "gemini-3.5-flash"

# # Align storage with RAG service (project-root/storage)
# BASE_DIR = Path(__file__).resolve().parent.parent.parent
# STORAGE_DIR = BASE_DIR / "storage"
# MAPPINGS_FILE = STORAGE_DIR / "pii_mappings.json"


# @dataclass
# class PiiMapping:
#     original: str
#     masked: str
#     type: str


# class PresidioService:
#     """
#     PII masking powered by Microsoft Presidio regex + Gemini LLM NER.
#     - Presidio (local): EMAIL, PHONE, CREDIT_CARD, US_SSN, IP_ADDRESS
#     - Gemini (cloud): PERSON, ORGANIZATION, LOCATION
#     - Persistence: Key-value mappings stored in storage/pii_mappings.json
#     """

#     _mapping_store: Dict[str, PiiMapping] = {}
#     _counter_map: Dict[str, int] = {}
#     _presidio_recognizers: List = []
#     _initialized: bool = False

#     @classmethod
#     def _ensure_storage(cls) -> None:
#         STORAGE_DIR.mkdir(parents=True, exist_ok=True)

#     @classmethod
#     def _load_mappings(cls) -> None:
#         if not MAPPINGS_FILE.exists():
#             cls._mapping_store = {}
#             cls._counter_map = {}
#             return
#         try:
#             with open(MAPPINGS_FILE, "r", encoding="utf-8") as f:
#                 data = json.load(f)
#             cls._mapping_store = {
#                 k: PiiMapping(**v) for k, v in data.get("mappings", {}).items()
#             }
#             cls._counter_map = data.get("counters", {})
#         except Exception as e:
#             logger.error("[PresidioService] Failed to load PII mappings: %s", e)
#             cls._mapping_store = {}
#             cls._counter_map = {}

#     @classmethod
#     def _save_mappings(cls) -> None:
#         cls._ensure_storage()
#         try:
#             with open(MAPPINGS_FILE, "w", encoding="utf-8") as f:
#                 json.dump(
#                     {
#                         "mappings": {k: asdict(v) for k, v in cls._mapping_store.items()},
#                         "counters": cls._counter_map,
#                     },
#                     f,
#                     indent=2,
#                     ensure_ascii=False,
#                 )
#         except Exception as e:
#             logger.error("[PresidioService] Failed to save PII mappings: %s", e)

#     @classmethod
#     def _init_engine(cls) -> None:
#         if cls._initialized:
#             return
#         try:
#             cls._presidio_recognizers = [
#                 EmailRecognizer(),
#                 PhoneRecognizer(),
#                 CreditCardRecognizer(),
#                 UsSsnRecognizer(),
#                 IpRecognizer(),
#             ]
#             cls._load_mappings()
#             cls._initialized = True
#             logger.info("[PresidioService] Presidio regex recognizers initialized.")
#         except Exception as e:
#             logger.error("[PresidioService] Failed to initialize recognizers: %s", e)
#             raise

#     @classmethod
#     def _get_placeholder(cls, entity_type: str, original: str) -> str:
#         cls._load_mappings()
#         for placeholder, mapping in cls._mapping_store.items():
#             if mapping.original == original and mapping.type == entity_type:
#                 return placeholder

#         current_count = cls._counter_map.get(entity_type, 0)
#         placeholder = f"<{entity_type}_{current_count}>"
#         cls._counter_map[entity_type] = current_count + 1

#         cls._mapping_store[placeholder] = PiiMapping(
#             original=original, masked=placeholder, type=entity_type
#         )
#         cls._save_mappings()
#         return placeholder

#     # -------------------------------------------------------------
#     # Main masking entry point (async signature preserved for RAG)
#     # -------------------------------------------------------------
#     @classmethod
#     async def mask_advanced_pii(cls, text: str, api_key: Optional[str] = None) -> str:
#         if not text or not text.strip():
#             return text

#         try:
#             cls._init_engine()
#             entities: List[Dict] = []

#             # ---- Tier 1: Presidio regex-based detection (local, no API key) ----
#             for recognizer in cls._presidio_recognizers:
#                 results = recognizer.analyze(
#                     text=text, entities=recognizer.supported_entities
#                 )
#                 for r in results:
#                     entity_text = text[r.start : r.end]
#                     entities.append(
#                         {
#                             "text": entity_text,
#                             "type": r.entity_type,
#                         }
#                     )

#             # ---- Tier 2: Gemini LLM NER for PERSON, ORGANIZATION, LOCATION ----
#             if api_key:
#                 try:
#                     client = genai.Client(api_key=api_key)
#                     prompt = f"""You are the NER (Named Entity Recognition) engine of Microsoft Presidio PII Protection system.
# Analyze the following text and extract sensitive entities to mask.
# Extract only:
# - PERSON (Full names or single names of people, e.g., "John Doe")
# - ORGANIZATION (Company names, institutions, e.g., "Acme Corp")
# - LOCATION (Addresses, cities, specific places, e.g., "123 Main St", "London")

# Do NOT extract generic words or non-PII terms.

# Text to analyze:
# \"\"\"
# {text}
# \"\"\"

# Return your findings in valid JSON format only, matching this structure:
# {{
#   "entities": [
#     {{ "text": "entity text to mask", "type": "PERSON" | "ORGANIZATION" | "LOCATION" }}
#   ]
# }}"""

#                     response = client.models.generate_content(
#                         model=GEMINI_MODEL,
#                         contents=prompt,
#                         config=types.GenerateContentConfig(
#                             response_mime_type="application/json",
#                             temperature=0.1,
#                         ),
#                     )

#                     response_text = response.text or "{}"
#                     data = json.loads(response_text)
#                     llm_entities = data.get("entities") or []

#                     for entity in llm_entities:
#                         entity_text = entity.get("text", "")
#                         if entity_text and len(entity_text.strip()) >= 2:
#                             entities.append(
#                                 {
#                                     "text": entity_text,
#                                     "type": entity.get("type", "UNKNOWN"),
#                                 }
#                             )

#                 except Exception as error:
#                     logger.error("[PresidioService] Gemini NER error: %s", error)
#                     # Continue with regex-only results

#             # ---- Deduplicate by (text, type) ----
#             seen: Set[Tuple[str, str]] = set()
#             unique_entities = []
#             for e in entities:
#                 key = (e["text"].lower(), e["type"])
#                 if key not in seen:
#                     seen.add(key)
#                     unique_entities.append(e)

#             # Sort by length descending to prevent substring replacement conflicts
#             unique_entities.sort(key=lambda e: len(e["text"]), reverse=True)

#             # ---- Apply masking ----
#             masked = text
#             for entity in unique_entities:
#                 entity_text = entity["text"]
#                 if not entity_text or len(entity_text.strip()) < 2:
#                     continue

#                 escaped = re.escape(entity_text)
#                 pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
#                 entity_type = entity["type"]
#                 placeholder = cls._get_placeholder(entity_type, entity_text)

#                 masked = pattern.sub(placeholder, masked)

#             return masked

#         except Exception as error:
#             logger.error("[PresidioService] PII masking error: %s", error)
#             return text

#     # -------------------------------------------------------------
#     # Re-identification (demasking)
#     # -------------------------------------------------------------
#     @classmethod
#     def demask_text(cls, text: str) -> str:
#         if not text:
#             return text

#         cls._load_mappings()
#         demasked = text

#         placeholders = sorted(cls._mapping_store.keys(), key=len, reverse=True)
#         for placeholder in placeholders:
#             mapping = cls._mapping_store.get(placeholder)
#             if mapping:
#                 demasked = demasked.replace(placeholder, mapping.original)

#         return demasked

#     # -------------------------------------------------------------
#     # Accessors
#     # -------------------------------------------------------------
#     @classmethod
#     def get_mappings(cls) -> List[dict]:
#         cls._load_mappings()
#         return [asdict(m) for m in cls._mapping_store.values()]

#     @classmethod
#     def clear_mappings(cls) -> None:
#         cls._mapping_store.clear()
#         cls._counter_map.clear()
#         if MAPPINGS_FILE.exists():
#             try:
#                 MAPPINGS_FILE.unlink()
#                 logger.info("[PresidioService] Cleared persisted PII mappings.")
#             except Exception as e:
#                 logger.error("[PresidioService] Failed to delete mappings file: %s", e)

"""
Enterprise PII Detection & Masking Service.
Presidio SDK regex + NLP-backed recognizers (via AnalyzerEngine/RecognizerRegistry):
EMAIL, PHONE, CREDIT_CARD, SSN, IP_ADDRESS, PERSON, ORGANIZATION, LOCATION, etc.
Uses Presidio's default spaCy-backed NLP engine (en_core_web_lg).
"""
import json
import logging
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry

logger = logging.getLogger(__name__)

# Align storage with RAG service (project-root/storage)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "storage"
MAPPINGS_FILE = STORAGE_DIR / "pii_mappings.json"


@dataclass
class PiiMapping:
    original: str
    masked: str
    type: str


class PresidioService:
    """
    PII masking powered by Presidio's default AnalyzerEngine.
    - Regex/pattern recognizers: EMAIL, PHONE, CREDIT_CARD, US_SSN, IP_ADDRESS, etc.
    - spaCy-backed NLP recognizer: PERSON, ORGANIZATION (ORG), LOCATION (GPE/LOC), etc.
    - Persistence: Key-value mappings stored in storage/pii_mappings.json
    """

    _mapping_store: Dict[str, PiiMapping] = {}
    _counter_map: Dict[str, int] = {}
    _analyzer: Optional[AnalyzerEngine] = None
    _initialized: bool = False

    @classmethod
    def _ensure_storage(cls) -> None:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _load_mappings(cls) -> None:
        if not MAPPINGS_FILE.exists():
            cls._mapping_store = {}
            cls._counter_map = {}
            return
        try:
            with open(MAPPINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cls._mapping_store = {
                k: PiiMapping(**v) for k, v in data.get("mappings", {}).items()
            }
            cls._counter_map = data.get("counters", {})
        except Exception as e:
            logger.error("[PresidioService] Failed to load PII mappings: %s", e)
            cls._mapping_store = {}
            cls._counter_map = {}

    @classmethod
    def _save_mappings(cls) -> None:
        cls._ensure_storage()
        try:
            with open(MAPPINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "mappings": {k: asdict(v) for k, v in cls._mapping_store.items()},
                        "counters": cls._counter_map,
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception as e:
            logger.error("[PresidioService] Failed to save PII mappings: %s", e)

    @classmethod
    def _init_engine(cls) -> None:
        if cls._initialized:
            return
        try:
            registry = RecognizerRegistry()
            registry.load_predefined_recognizers(languages=["en"])

            # No custom nlp_engine passed in => Presidio builds its default
            # spaCy-backed engine (en_core_web_lg), which is now installed.
            # SpacyRecognizer is kept in the registry so PERSON/ORG/LOCATION
            # get detected via spaCy NER, in addition to the regex recognizers.
            cls._analyzer = AnalyzerEngine(registry=registry)

            cls._load_mappings()
            cls._initialized = True
            logger.info("[PresidioService] Presidio AnalyzerEngine initialized with default spaCy NLP engine.")
        except Exception as e:
            logger.error("[PresidioService] Failed to initialize recognizers: %s", e)
            raise

    @classmethod
    def _get_placeholder(cls, entity_type: str, original: str) -> str:
        cls._load_mappings()
        for placeholder, mapping in cls._mapping_store.items():
            if mapping.original == original and mapping.type == entity_type:
                return placeholder

        current_count = cls._counter_map.get(entity_type, 0)
        placeholder = f"<{entity_type}_{current_count}>"
        cls._counter_map[entity_type] = current_count + 1

        cls._mapping_store[placeholder] = PiiMapping(
            original=original, masked=placeholder, type=entity_type
        )
        cls._save_mappings()
        return placeholder

    # -------------------------------------------------------------
    # Main masking entry point (async signature preserved for RAG)
    # -------------------------------------------------------------
    @classmethod
    async def mask_advanced_pii(cls, text: str, api_key: Optional[str] = None) -> str:
        """
        `api_key` is no longer used now that detection is fully local via
        Presidio's default AnalyzerEngine (regex recognizers + spaCy NER).
        It's kept as an accepted (ignored) parameter so existing call sites
        (e.g. RagService) don't need to change their call signature.
        """
        if not text or not text.strip():
            return text

        try:
            cls._init_engine()
            entities: List[Dict] = []

            # ---- Presidio: regex recognizers + spaCy-backed NER recognizer ----
            results = cls._analyzer.analyze(
                text=text,
                language="en",
            )

            for r in results:
                entities.append(
                    {
                        "text": text[r.start : r.end],
                        "type": r.entity_type,
                    }
                )

            # ---- Deduplicate by (text, type) ----
            seen: Set[Tuple[str, str]] = set()
            unique_entities = []
            for e in entities:
                key = (e["text"].lower(), e["type"])
                if key not in seen:
                    seen.add(key)
                    unique_entities.append(e)

            # Sort by length descending to prevent substring replacement conflicts
            unique_entities.sort(key=lambda e: len(e["text"]), reverse=True)

            # ---- Apply masking ----
            masked = text
            for entity in unique_entities:
                entity_text = entity["text"]
                if not entity_text or len(entity_text.strip()) < 2:
                    continue

                escaped = re.escape(entity_text)
                pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
                entity_type = entity["type"]
                placeholder = cls._get_placeholder(entity_type, entity_text)

                masked = pattern.sub(placeholder, masked)

            return masked

        except Exception as error:
            logger.error("[PresidioService] PII masking error: %s", error)
            return text

    # -------------------------------------------------------------
    # Re-identification (demasking)
    # -------------------------------------------------------------
    @classmethod
    def demask_text(cls, text: str) -> str:
        if not text:
            return text

        cls._load_mappings()
        demasked = text

        placeholders = sorted(cls._mapping_store.keys(), key=len, reverse=True)
        for placeholder in placeholders:
            mapping = cls._mapping_store.get(placeholder)
            if mapping:
                demasked = demasked.replace(placeholder, mapping.original)

        return demasked

    # -------------------------------------------------------------
    # Accessors
    # -------------------------------------------------------------
    @classmethod
    def get_mappings(cls) -> List[dict]:
        cls._load_mappings()
        return [asdict(m) for m in cls._mapping_store.values()]

    @classmethod
    def clear_mappings(cls) -> None:
        cls._mapping_store.clear()
        cls._counter_map.clear()
        if MAPPINGS_FILE.exists():
            try:
                MAPPINGS_FILE.unlink()
                logger.info("[PresidioService] Cleared persisted PII mappings.")
            except Exception as e:
                logger.error("[PresidioService] Failed to delete mappings file: %s", e)