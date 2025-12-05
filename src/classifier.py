"""
LLM-based ticket classifier for the Ticket Automation System.

Uses OpenAI-compatible API to classify helpdesk requests against
the Service Catalog with structured output.

Implements graceful degradation when:
- LLM returns non-existent categories
- Service catalog changes
- API errors occur
"""

import logging
from difflib import SequenceMatcher
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from .config import LLMConfig
from .models import (
    ClassificationResult,
    HelpdeskRequest,
    ServiceCatalog,
    SLA,
)


logger = logging.getLogger(__name__)


class ClassificationError(Exception):
    """Error during ticket classification."""
    pass


class LLMClassificationResponse(BaseModel):
    """Structured output schema for LLM classification."""
    
    request_category: str = Field(
        description="The category name from the Service Catalog that best matches the request"
    )
    request_type: str = Field(
        description="The specific request type within the category"
    )
    confidence: float = Field(
        ge=0.0, 
        le=1.0,
        description="Confidence score from 0 to 1"
    )
    reasoning: str = Field(
        description="Brief explanation for why this classification was chosen"
    )


# System prompt with careful instructions for accurate classification
SYSTEM_PROMPT = """You are an expert IT Service Desk analyst responsible for classifying incoming support requests.

Your task is to analyze each helpdesk ticket and assign it to the most appropriate Category and Request Type from the provided Service Catalog.

## CRITICAL INSTRUCTIONS:

1. **USE ONLY categories and request types from the Service Catalog provided in the user message.**
   Do NOT invent new categories. Use EXACT names from the catalog.

2. **Classification Strategy**:
   - First, identify the PRIMARY issue from the ticket description
   - Then, find the best matching category
   - Finally, select the most specific request type within that category

3. **Priority Rules** (when multiple categories could apply):
   - Security incidents (phishing, lost/stolen devices) → Security category FIRST
   - Authentication issues (password, MFA) → Access Management
   - Physical equipment → Hardware Support
   - Software/licenses → Software & Licensing
   - Network/connectivity → Network & Connectivity
   - Employee lifecycle → HR & Onboarding
   - Cannot determine → Other/Uncategorized

4. **Software & Licensing - Important Distinctions**:
   - SaaS apps errors/outages (Jira, Salesforce, Zoom, Slack, etc.) → "SaaS Platform Access"
   - Need to install software (VS Code, Docker, Python) → "Software Installation Issue"
   - Need a license (Adobe, Tableau, Office) → "Request New Software License"
   - Other software problems → "Other Software Issue"

5. **Hardware Support - Important Distinctions**:
   - Peripherals (mouse, keyboard, monitor, cables, headset) → "Peripheral Request (Mouse/Keyboard/Monitor)"
   - Laptop/desktop issues (won't turn on, slow, broken screen) → "Laptop Repair/Replacement"
   - Printer issues (offline, paper jam, can't print) → "Other Hardware Request"
   - Mobile device issues → "Mobile Device Issue"
   - Other hardware → "Other Hardware Request"

6. **Confidence Scoring**:
   - 0.9-1.0: Perfect match, no ambiguity
   - 0.7-0.9: Good match, minor interpretation needed
   - 0.5-0.7: Reasonable guess, multiple categories possible
   - <0.5: Uncertain, using best effort

7. **Reasoning**: Always explain WHY you chose this classification in 1-2 sentences.

## EXAMPLES:

Example 1:
- Input: "Forgot my Okta password"
- Category: "Access Management"
- Type: "Reset forgotten password"
- Confidence: 0.95
- Reasoning: "User explicitly states password issue with Okta authentication system."

Example 2:
- Input: "Lost my work phone in a taxi"
- Category: "Security"
- Type: "Report Lost/Stolen Device"
- Confidence: 0.95
- Reasoning: "Lost device is a security incident requiring immediate action to protect company data."

Example 3:
- Input: "Where is the cafeteria?"
- Category: "Other/Uncategorized"
- Type: "General Inquiry/Undefined"
- Confidence: 0.90
- Reasoning: "Non-IT request, not related to technical support services."

Example 4:
- Input: "Jira is down. I am getting a 500 error when loading Jira."
- Category: "Software & Licensing"
- Type: "SaaS Platform Access (Jira/Salesforce)"
- Confidence: 0.95
- Reasoning: "Jira is a SaaS platform, and user reports access/error issues, not installation."

Example 5:
- Input: "Need to install VS Code on my machine"
- Category: "Software & Licensing"
- Type: "Software Installation Issue"
- Confidence: 0.95
- Reasoning: "User explicitly requests software installation, not SaaS access."

Example 6:
- Input: "Need new monitor"
- Category: "Hardware Support"
- Type: "Peripheral Request (Mouse/Keyboard/Monitor)"
- Confidence: 0.95
- Reasoning: "Monitor is a peripheral device, matching the specific peripheral request type."

Example 7:
- Input: "The printer on the 3rd floor is offline"
- Category: "Hardware Support"
- Type: "Other Hardware Request"
- Confidence: 0.90
- Reasoning: "Printer is hardware equipment. No specific printer category, so Other Hardware Request."

Now classify the ticket provided in the user message using the Service Catalog listed there."""


def build_user_prompt(request: HelpdeskRequest, catalog: ServiceCatalog) -> str:
    """
    Build the user prompt for classification.
    
    Args:
        request: The helpdesk request to classify.
        catalog: The service catalog for reference.
        
    Returns:
        Formatted prompt string.
    """
    catalog_context = catalog.to_classification_context()
    
    return f"""{catalog_context}

---

## TICKET TO CLASSIFY:

**ID**: {request.id}
**Short Description**: {request.short_description}
**Full Description**: {request.long_description}
**Requester**: {request.requester_email}

---

Analyze this ticket and provide the classification. Use EXACT category and request type names from the Service Catalog above."""


class TicketClassifier:
    """
    LLM-based classifier for IT helpdesk tickets.
    
    Uses OpenAI's API with structured output to ensure consistent,
    parseable classification results.
    
    Implements graceful degradation:
    - Fuzzy matching for category/type names (handles LLM variations)
    - Default SLA when lookup fails
    - Fallback to "Other/Uncategorized" on classification failure
    """
    
    # Default fallback values
    FALLBACK_CATEGORY = "Other/Uncategorized"
    FALLBACK_TYPE = "General Inquiry/Undefined"
    FALLBACK_SLA = SLA(unit="hours", value=24)
    
    # Minimum similarity threshold for fuzzy matching (0.0 - 1.0)
    SIMILARITY_THRESHOLD = 0.7
    
    def __init__(self, config: LLMConfig, catalog: ServiceCatalog):
        """
        Initialize the classifier.
        
        Args:
            config: LLM configuration.
            catalog: Service catalog for classification reference.
        """
        self._config = config
        self._catalog = catalog
        
        # Build lookup caches for fuzzy matching
        # Note: Category names should be unique (enforced by data_sources.py)
        self._category_names = [cat.name for cat in catalog.categories]
        self._type_names_by_category: dict[str, list[str]] = {}
        
        for cat in catalog.categories:
            if cat.name in self._type_names_by_category:
                # Merge request types if somehow duplicate category exists
                self._type_names_by_category[cat.name].extend(
                    req.name for req in cat.requests
                )
                logger.warning(f"Duplicate category '{cat.name}' detected, merging request types")
            else:
                self._type_names_by_category[cat.name] = [req.name for req in cat.requests]
        
        # Initialize OpenAI client
        client_kwargs = {
            "api_key": config.api_key,
        }
        if config.api_base_url:
            client_kwargs["base_url"] = config.api_base_url
            
        self._client = OpenAI(**client_kwargs)
        
        logger.info(f"Initialized classifier with model: {config.model}")
        logger.info(f"Catalog loaded: {len(catalog.categories)} categories")
    
    def _find_best_match(self, query: str, candidates: list[str]) -> Optional[str]:
        """
        Find the best matching string from candidates using fuzzy matching.
        
        Args:
            query: The string to match.
            candidates: List of possible matches.
            
        Returns:
            Best matching candidate or None if no good match found.
        """
        if not candidates:
            return None
        
        query_lower = query.lower().strip()
        
        # Try exact match first (case-insensitive)
        for candidate in candidates:
            if candidate.lower() == query_lower:
                return candidate
        
        # Try fuzzy matching
        best_match = None
        best_score = 0.0
        
        for candidate in candidates:
            score = SequenceMatcher(None, query_lower, candidate.lower()).ratio()
            if score > best_score:
                best_score = score
                best_match = candidate
        
        if best_score >= self.SIMILARITY_THRESHOLD:
            if best_score < 1.0:
                logger.debug(f"Fuzzy matched '{query}' -> '{best_match}' (score: {best_score:.2f})")
            return best_match
        
        return None
    
    def _find_category_for_type(self, type_name: str) -> Optional[str]:
        """
        Find which category a request type belongs to.
        
        Args:
            type_name: The request type name to look up.
            
        Returns:
            Category name or None if not found.
        """
        for cat_name, types in self._type_names_by_category.items():
            if type_name in types:
                return cat_name
        return None
    
    def _normalize_classification(
        self, 
        category: str, 
        request_type: str
    ) -> tuple[str, str]:
        """
        Normalize LLM output to match actual catalog entries.
        
        Handles cases where LLM returns:
        - Slightly different names than in the catalog
        - Request type in the category field (common LLM mistake)
        - Category in the request type field
        
        Args:
            category: Raw category from LLM.
            request_type: Raw request type from LLM.
            
        Returns:
            Tuple of (normalized_category, normalized_type).
        """
        # Build list of all request types for cross-checking
        all_types = [t for types in self._type_names_by_category.values() for t in types]
        
        # Step 1: Try to find category directly
        matched_category = self._find_best_match(category, self._category_names)
        
        if not matched_category:
            # LLM might have put request_type in category field - check if it's a type
            matched_as_type = self._find_best_match(category, all_types)
            if matched_as_type:
                # Found! The "category" is actually a request type
                matched_category = self._find_category_for_type(matched_as_type)
                logger.debug(
                    f"LLM returned type '{category}' as category, "
                    f"resolved to category '{matched_category}'"
                )
                # Use the found type, ignore the original request_type if it matches
                if matched_category:
                    return matched_category, matched_as_type
            
            # Still not found - use fallback
            logger.warning(
                f"Category '{category}' not found in catalog, using fallback"
            )
            return self.FALLBACK_CATEGORY, self.FALLBACK_TYPE
        
        # Step 2: Find best matching type within the matched category
        type_candidates = self._type_names_by_category.get(matched_category, [])
        matched_type = self._find_best_match(request_type, type_candidates)
        
        if not matched_type:
            # Try to find type in any category as fallback
            matched_type = self._find_best_match(request_type, all_types)
            
            if matched_type:
                # Find which category this type belongs to
                correct_category = self._find_category_for_type(matched_type)
                if correct_category and correct_category != matched_category:
                    logger.debug(
                        f"Type '{request_type}' found in category '{correct_category}' "
                        f"(LLM said '{matched_category}')"
                    )
                    matched_category = correct_category
            else:
                logger.warning(
                    f"Request type '{request_type}' not found, using fallback for category '{matched_category}'"
                )
                # Use first type in category or fallback
                matched_type = type_candidates[0] if type_candidates else self.FALLBACK_TYPE
        
        return matched_category, matched_type
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying classification after error: {retry_state.outcome.exception()}"
        ),
    )
    def classify_request(self, request: HelpdeskRequest) -> ClassificationResult:
        """
        Classify a single helpdesk request.
        
        Args:
            request: The request to classify.
            
        Returns:
            ClassificationResult with category, type, and SLA.
            
        Raises:
            ClassificationError: If classification fails after retries.
        """
        logger.debug(f"Classifying request: {request.id}")
        
        try:
            user_prompt = build_user_prompt(request, self._catalog)
            
            response = self._client.beta.chat.completions.parse(
                model=self._config.model,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=LLMClassificationResponse,
            )
            
            parsed = response.choices[0].message.parsed
            
            if not parsed:
                raise ClassificationError(f"Empty response for request {request.id}")
            
            result = ClassificationResult(
                request_category=parsed.request_category,
                request_type=parsed.request_type,
                confidence=parsed.confidence,
                reasoning=parsed.reasoning,
            )
            
            logger.debug(
                f"Classified {request.id}: {result.request_category} / "
                f"{result.request_type} (confidence: {result.confidence:.2f})"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Classification error for {request.id}: {e}")
            raise ClassificationError(f"Failed to classify {request.id}: {e}") from e
    
    def classify_and_update(self, request: HelpdeskRequest) -> HelpdeskRequest:
        """
        Classify a request and return an updated copy with classification.
        
        Implements graceful degradation:
        - Normalizes LLM output to match catalog
        - Falls back to defaults if lookup fails
        
        Args:
            request: The request to classify.
            
        Returns:
            Updated HelpdeskRequest with filled classification fields.
        """
        result = self.classify_request(request)
        
        # Normalize classification to match actual catalog entries
        category, request_type = self._normalize_classification(
            result.request_category,
            result.request_type
        )
        
        # Look up SLA from catalog
        sla = self._catalog.get_request_type_sla(category, request_type)
        
        if not sla:
            logger.warning(
                f"SLA not found for {category}/{request_type}, using default 24h"
            )
            sla = self.FALLBACK_SLA
        
        # Update request with classification
        request.request_category = category
        request.request_type = request_type
        request.sla = sla
        
        return request
    
    def classify_batch(
        self, 
        requests: list[HelpdeskRequest],
        batch_size: int = 5,
    ) -> list[HelpdeskRequest]:
        """
        Classify multiple requests with progress logging.
        
        Args:
            requests: List of requests to classify.
            batch_size: Number of requests to process before logging progress.
            
        Returns:
            List of classified requests.
        """
        total = len(requests)
        classified = []
        
        logger.info(f"Starting classification of {total} requests")
        
        for i, request in enumerate(requests, 1):
            try:
                classified_request = self.classify_and_update(request)
                classified.append(classified_request)
                
                if i % batch_size == 0 or i == total:
                    logger.info(f"Progress: {i}/{total} requests classified")
                    
            except ClassificationError as e:
                logger.error(f"Failed to classify request {request.id}: {e}")
                # Assign to fallback category on failure - don't break the pipeline
                request.request_category = self.FALLBACK_CATEGORY
                request.request_type = self.FALLBACK_TYPE
                request.sla = self.FALLBACK_SLA
                classified.append(request)
        
        logger.info(f"Classification complete: {len(classified)} requests processed")
        return classified

