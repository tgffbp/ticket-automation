"""
LLM-based ticket classifier for the Ticket Automation System.

Uses OpenAI-compatible API to classify helpdesk requests against
the Service Catalog with structured output.
"""

import asyncio
import logging
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

Your task is to analyze each helpdesk ticket and assign it to the most appropriate Category and Request Type from the Service Catalog.

## Classification Rules:

1. **Exact Match First**: If the request clearly matches a specific request type, use it.

2. **Category Priority**: Consider the primary issue:
   - Password/login issues → "Access Management"
   - Physical devices (laptop, monitor, keyboard, mouse) → "Hardware Support"
   - Software licenses or installations → "Software & Licensing"
   - VPN, WiFi, firewall → "Network & Connectivity"
   - Phishing, lost/stolen devices, security concerns → "Security"
   - New hires, offboarding → "HR & Onboarding"
   - Anything else → "Other/Uncategorized"

3. **Request Type Selection**: Choose the most specific matching request type within the category.

4. **Edge Cases**:
   - Non-IT requests (cafeteria location, coffee machines) → "Other/Uncategorized" → "General Inquiry/Undefined"
   - Lost/stolen devices → "Security" → "Report Lost/Stolen Device" (security takes priority)
   - MFA issues → "Access Management" → "Multi-Factor Authentication (MFA) Reset"
   - Application errors (Jira, Salesforce) → "Software & Licensing" → "SaaS Platform Access (Jira/Salesforce)"

5. **Confidence Score**:
   - 0.9-1.0: Clear, unambiguous match
   - 0.7-0.9: Good match with minor ambiguity
   - 0.5-0.7: Reasonable match, could fit multiple categories
   - <0.5: Uncertain, defaulting to best guess

Always provide a brief reasoning for your classification."""


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
    """
    
    def __init__(self, config: LLMConfig, catalog: ServiceCatalog):
        """
        Initialize the classifier.
        
        Args:
            config: LLM configuration.
            catalog: Service catalog for classification reference.
        """
        self._config = config
        self._catalog = catalog
        
        # Initialize OpenAI client
        client_kwargs = {
            "api_key": config.api_key,
        }
        if config.api_base_url:
            client_kwargs["base_url"] = config.api_base_url
            
        self._client = OpenAI(**client_kwargs)
        
        logger.info(f"Initialized classifier with model: {config.model}")
    
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
        
        Args:
            request: The request to classify.
            
        Returns:
            Updated HelpdeskRequest with filled classification fields.
        """
        result = self.classify_request(request)
        
        # Look up SLA from catalog
        sla = self._catalog.get_request_type_sla(
            result.request_category, 
            result.request_type
        )
        
        if not sla:
            logger.warning(
                f"Could not find SLA for {result.request_category} / {result.request_type}"
            )
            sla = SLA(unit="hours", value=24)  # Default SLA
        
        # Update request with classification
        request.request_category = result.request_category
        request.request_type = result.request_type
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
                # Assign to Other/Uncategorized on failure
                request.request_category = "Other/Uncategorized"
                request.request_type = "General Inquiry/Undefined"
                request.sla = SLA(unit="hours", value=0)
                classified.append(request)
        
        logger.info(f"Classification complete: {len(classified)} requests processed")
        return classified

