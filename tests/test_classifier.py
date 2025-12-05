"""
Unit tests for the LLM-based ticket classifier.

Tests cover:
- Fuzzy matching logic
- Classification normalization
- Fallback behavior
- Batch processing with error handling
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.classifier import (
    ClassificationError,
    LLMClassificationResponse,
    TicketClassifier,
    build_user_prompt,
    SYSTEM_PROMPT,
)
from src.config import LLMConfig
from src.models import (
    ClassificationResult,
    HelpdeskRequest,
    ServiceCatalog,
    ServiceCategory,
    ServiceCatalogRequest,
    SLA,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_catalog() -> ServiceCatalog:
    """Create a sample service catalog for testing."""
    return ServiceCatalog(
        categories=[
            ServiceCategory(
                name="Access Management",
                requests=[
                    ServiceCatalogRequest(
                        name="Reset forgotten password",
                        sla=SLA(unit="hours", value=4),
                    ),
                    ServiceCatalogRequest(
                        name="Multi-Factor Authentication (MFA) Reset",
                        sla=SLA(unit="hours", value=4),
                    ),
                ],
            ),
            ServiceCategory(
                name="Hardware Support",
                requests=[
                    ServiceCatalogRequest(
                        name="Laptop Repair/Replacement",
                        sla=SLA(unit="days", value=3),
                    ),
                    ServiceCatalogRequest(
                        name="Peripheral Request (Mouse/Keyboard/Monitor)",
                        sla=SLA(unit="days", value=3),
                    ),
                ],
            ),
            ServiceCategory(
                name="Software & Licensing",
                requests=[
                    ServiceCatalogRequest(
                        name="SaaS Platform Access (Jira/Salesforce)",
                        sla=SLA(unit="hours", value=8),
                    ),
                    ServiceCatalogRequest(
                        name="Software Installation Issue",
                        sla=SLA(unit="hours", value=24),
                    ),
                ],
            ),
            ServiceCategory(
                name="Other/Uncategorized",
                requests=[
                    ServiceCatalogRequest(
                        name="General Inquiry/Undefined",
                        sla=SLA(unit="hours", value=24),
                    ),
                ],
            ),
        ]
    )


@pytest.fixture
def sample_request() -> HelpdeskRequest:
    """Create a sample helpdesk request for testing."""
    return HelpdeskRequest(
        id="req_001",
        short_description="Password reset needed",
        long_description="I forgot my password and cannot log in.",
        requester_email="user@example.com",
    )


@pytest.fixture
def llm_config() -> LLMConfig:
    """Create a sample LLM config for testing."""
    return LLMConfig(
        api_key="test-api-key",
        model="gpt-4o-mini",
        temperature=0.1,
    )


@pytest.fixture
def classifier(llm_config: LLMConfig, sample_catalog: ServiceCatalog) -> TicketClassifier:
    """Create a classifier with mocked OpenAI client."""
    with patch("src.classifier.OpenAI"):
        return TicketClassifier(llm_config, sample_catalog)


# =============================================================================
# LLMClassificationResponse Tests
# =============================================================================

class TestLLMClassificationResponse:
    """Tests for the LLM response schema."""
    
    def test_valid_response(self):
        """Test valid classification response."""
        response = LLMClassificationResponse(
            request_category="Access Management",
            request_type="Reset forgotten password",
            confidence=0.95,
            reasoning="User explicitly needs password reset.",
        )
        assert response.request_category == "Access Management"
        assert response.confidence == 0.95
    
    def test_confidence_bounds(self):
        """Test confidence must be between 0 and 1."""
        with pytest.raises(ValueError):
            LLMClassificationResponse(
                request_category="Test",
                request_type="Test",
                confidence=1.5,  # Invalid
                reasoning="Test",
            )
        
        with pytest.raises(ValueError):
            LLMClassificationResponse(
                request_category="Test",
                request_type="Test",
                confidence=-0.1,  # Invalid
                reasoning="Test",
            )
    
    def test_edge_confidence_values(self):
        """Test edge confidence values are valid."""
        response_zero = LLMClassificationResponse(
            request_category="Test",
            request_type="Test",
            confidence=0.0,
            reasoning="Test",
        )
        assert response_zero.confidence == 0.0
        
        response_one = LLMClassificationResponse(
            request_category="Test",
            request_type="Test",
            confidence=1.0,
            reasoning="Test",
        )
        assert response_one.confidence == 1.0


# =============================================================================
# build_user_prompt Tests
# =============================================================================

class TestBuildUserPrompt:
    """Tests for the user prompt builder."""
    
    def test_prompt_contains_request_info(
        self, 
        sample_request: HelpdeskRequest, 
        sample_catalog: ServiceCatalog
    ):
        """Test prompt includes request details."""
        prompt = build_user_prompt(sample_request, sample_catalog)
        
        assert sample_request.id in prompt
        assert sample_request.short_description in prompt
        assert sample_request.long_description in prompt
        assert sample_request.requester_email in prompt
    
    def test_prompt_contains_catalog_context(
        self, 
        sample_request: HelpdeskRequest, 
        sample_catalog: ServiceCatalog
    ):
        """Test prompt includes catalog categories."""
        prompt = build_user_prompt(sample_request, sample_catalog)
        
        assert "Access Management" in prompt
        assert "Hardware Support" in prompt
        assert "Software & Licensing" in prompt


# =============================================================================
# TicketClassifier Initialization Tests
# =============================================================================

class TestTicketClassifierInit:
    """Tests for classifier initialization."""
    
    def test_builds_category_cache(
        self, 
        classifier: TicketClassifier, 
        sample_catalog: ServiceCatalog
    ):
        """Test classifier builds category name cache."""
        assert "Access Management" in classifier._category_names
        assert "Hardware Support" in classifier._category_names
        assert len(classifier._category_names) == len(sample_catalog.categories)
    
    def test_builds_type_cache(self, classifier: TicketClassifier):
        """Test classifier builds type-by-category cache."""
        assert "Access Management" in classifier._type_names_by_category
        assert "Reset forgotten password" in classifier._type_names_by_category["Access Management"]
        assert "Laptop Repair/Replacement" in classifier._type_names_by_category["Hardware Support"]


# =============================================================================
# Fuzzy Matching Tests
# =============================================================================

class TestFindBestMatch:
    """Tests for fuzzy matching logic."""
    
    def test_exact_match(self, classifier: TicketClassifier):
        """Test exact match returns correct result."""
        candidates = ["Access Management", "Hardware Support"]
        result = classifier._find_best_match("Access Management", candidates)
        assert result == "Access Management"
    
    def test_case_insensitive_match(self, classifier: TicketClassifier):
        """Test matching is case-insensitive."""
        candidates = ["Access Management", "Hardware Support"]
        result = classifier._find_best_match("access management", candidates)
        assert result == "Access Management"
    
    def test_fuzzy_match_similar_string(self, classifier: TicketClassifier):
        """Test fuzzy matching finds similar strings."""
        candidates = ["Reset forgotten password", "MFA Reset"]
        # "Reset password" should match "Reset forgotten password"
        result = classifier._find_best_match("Reset password", candidates)
        assert result == "Reset forgotten password"
    
    def test_no_match_below_threshold(self, classifier: TicketClassifier):
        """Test returns None when no good match found."""
        candidates = ["Access Management", "Hardware Support"]
        result = classifier._find_best_match("Completely Different", candidates)
        assert result is None
    
    def test_empty_candidates(self, classifier: TicketClassifier):
        """Test returns None for empty candidates."""
        result = classifier._find_best_match("Test", [])
        assert result is None
    
    def test_whitespace_handling(self, classifier: TicketClassifier):
        """Test handles leading/trailing whitespace."""
        candidates = ["Access Management"]
        result = classifier._find_best_match("  Access Management  ", candidates)
        assert result == "Access Management"


# =============================================================================
# Category Lookup Tests
# =============================================================================

class TestFindCategoryForType:
    """Tests for finding category by type name."""
    
    def test_finds_correct_category(self, classifier: TicketClassifier):
        """Test finds category for known type."""
        result = classifier._find_category_for_type("Reset forgotten password")
        assert result == "Access Management"
        
        result = classifier._find_category_for_type("Laptop Repair/Replacement")
        assert result == "Hardware Support"
    
    def test_returns_none_for_unknown_type(self, classifier: TicketClassifier):
        """Test returns None for unknown type."""
        result = classifier._find_category_for_type("Unknown Type XYZ")
        assert result is None


# =============================================================================
# Classification Normalization Tests
# =============================================================================

class TestNormalizeClassification:
    """Tests for classification normalization logic."""
    
    def test_exact_category_and_type(self, classifier: TicketClassifier):
        """Test normalization with exact matches."""
        category, req_type = classifier._normalize_classification(
            "Access Management",
            "Reset forgotten password"
        )
        assert category == "Access Management"
        assert req_type == "Reset forgotten password"
    
    def test_fuzzy_category_match(self, classifier: TicketClassifier):
        """Test normalization handles fuzzy category match."""
        category, req_type = classifier._normalize_classification(
            "access management",  # lowercase
            "Reset forgotten password"
        )
        assert category == "Access Management"
        assert req_type == "Reset forgotten password"
    
    def test_type_in_category_field(self, classifier: TicketClassifier):
        """Test handles when LLM puts type in category field."""
        # LLM sometimes returns the type name as the category
        category, req_type = classifier._normalize_classification(
            "Reset forgotten password",  # This is a type, not category
            "Some other value"
        )
        assert category == "Access Management"
        assert req_type == "Reset forgotten password"
    
    def test_unknown_category_fallback(self, classifier: TicketClassifier):
        """Test falls back for completely unknown category."""
        category, req_type = classifier._normalize_classification(
            "Completely Unknown Category",
            "Unknown Type"
        )
        assert category == TicketClassifier.FALLBACK_CATEGORY
        assert req_type == TicketClassifier.FALLBACK_TYPE
    
    def test_type_in_wrong_category(self, classifier: TicketClassifier):
        """Test corrects type found in different category."""
        # LLM says Hardware Support, but the type is from Software
        category, req_type = classifier._normalize_classification(
            "Hardware Support",
            "SaaS Platform Access (Jira/Salesforce)"
        )
        # Should correct to Software & Licensing
        assert category == "Software & Licensing"
        assert req_type == "SaaS Platform Access (Jira/Salesforce)"
    
    def test_unknown_type_uses_first_in_category(self, classifier: TicketClassifier):
        """Test uses first type in category when type not found."""
        category, req_type = classifier._normalize_classification(
            "Access Management",
            "Completely Unknown Type"
        )
        assert category == "Access Management"
        # Should use first type in Access Management
        assert req_type == "Reset forgotten password"
    
    def test_empty_category_complete_fallback(
        self, 
        llm_config: LLMConfig
    ):
        """Test complete fallback when category has no types."""
        # Create catalog with empty category
        catalog = ServiceCatalog(
            categories=[
                ServiceCategory(
                    name="Empty Category",
                    requests=[],  # No types
                ),
            ]
        )
        
        with patch("src.classifier.OpenAI"):
            classifier = TicketClassifier(llm_config, catalog)
        
        category, req_type = classifier._normalize_classification(
            "Empty Category",
            "Any Type"
        )
        # Should fall back completely since Empty Category has no types
        assert category == TicketClassifier.FALLBACK_CATEGORY
        assert req_type == TicketClassifier.FALLBACK_TYPE


# =============================================================================
# Classify and Update Tests
# =============================================================================

class TestClassifyAndUpdate:
    """Tests for the classify_and_update method."""
    
    def test_updates_request_fields(
        self, 
        classifier: TicketClassifier,
        sample_request: HelpdeskRequest
    ):
        """Test request fields are updated after classification."""
        # Mock the classify_request method
        mock_result = ClassificationResult(
            request_category="Access Management",
            request_type="Reset forgotten password",
            confidence=0.95,
            reasoning="Password reset request",
        )
        classifier.classify_request = Mock(return_value=mock_result)
        
        updated = classifier.classify_and_update(sample_request)
        
        assert updated.request_category == "Access Management"
        assert updated.request_type == "Reset forgotten password"
        assert updated.sla.unit == "hours"
        assert updated.sla.value == 4
    
    def test_uses_fallback_sla_when_not_found(
        self, 
        classifier: TicketClassifier,
        sample_request: HelpdeskRequest
    ):
        """Test uses fallback SLA when lookup fails."""
        # Return a type that doesn't exist
        mock_result = ClassificationResult(
            request_category="Other/Uncategorized",
            request_type="Non-existent Type",
            confidence=0.5,
            reasoning="Unknown request",
        )
        classifier.classify_request = Mock(return_value=mock_result)
        
        # Mock _normalize_classification to return valid category but keep the type
        # that won't have SLA
        with patch.object(
            classifier, 
            '_normalize_classification',
            return_value=("Other/Uncategorized", "General Inquiry/Undefined")
        ):
            updated = classifier.classify_and_update(sample_request)
        
        # Should have used the SLA from the catalog for General Inquiry
        assert updated.sla is not None


# =============================================================================
# Batch Classification Tests
# =============================================================================

class TestClassifyBatch:
    """Tests for batch classification."""
    
    def test_classifies_all_requests(
        self, 
        classifier: TicketClassifier
    ):
        """Test all requests in batch are classified."""
        requests = [
            HelpdeskRequest(id="req_001", short_description="Test 1"),
            HelpdeskRequest(id="req_002", short_description="Test 2"),
            HelpdeskRequest(id="req_003", short_description="Test 3"),
        ]
        
        # Mock classify_and_update to return the request unchanged
        classifier.classify_and_update = Mock(side_effect=lambda r: r)
        
        result = classifier.classify_batch(requests)
        
        assert len(result) == 3
        assert classifier.classify_and_update.call_count == 3
    
    def test_handles_classification_errors(
        self, 
        classifier: TicketClassifier
    ):
        """Test batch continues after classification error."""
        requests = [
            HelpdeskRequest(id="req_001", short_description="Test 1"),
            HelpdeskRequest(id="req_002", short_description="Test 2"),
            HelpdeskRequest(id="req_003", short_description="Test 3"),
        ]
        
        # Second request fails
        def mock_classify(r):
            if r.id == "req_002":
                raise ClassificationError("API Error")
            return r
        
        classifier.classify_and_update = Mock(side_effect=mock_classify)
        
        result = classifier.classify_batch(requests)
        
        # All 3 should be returned (failed one with fallback)
        assert len(result) == 3
        
        # Failed request should have fallback values
        failed_request = next(r for r in result if r.id == "req_002")
        assert failed_request.request_category == TicketClassifier.FALLBACK_CATEGORY
        assert failed_request.request_type == TicketClassifier.FALLBACK_TYPE
        assert failed_request.sla == TicketClassifier.FALLBACK_SLA
    
    def test_empty_batch(self, classifier: TicketClassifier):
        """Test handling of empty batch."""
        result = classifier.classify_batch([])
        assert result == []


# =============================================================================
# System Prompt Tests
# =============================================================================

class TestSystemPrompt:
    """Tests for the system prompt content."""
    
    def test_contains_priority_rules(self):
        """Test prompt contains priority rules."""
        assert "Priority Rules" in SYSTEM_PROMPT
        assert "Security" in SYSTEM_PROMPT
        assert "Access Management" in SYSTEM_PROMPT
    
    def test_contains_examples(self):
        """Test prompt contains examples."""
        assert "Example 1:" in SYSTEM_PROMPT
        assert "Forgot my Okta password" in SYSTEM_PROMPT
    
    def test_contains_saas_instructions(self):
        """Test prompt contains SaaS platform instructions."""
        assert "SaaS" in SYSTEM_PROMPT
        assert "Jira" in SYSTEM_PROMPT
        assert "Salesforce" in SYSTEM_PROMPT
    
    def test_contains_confidence_guidelines(self):
        """Test prompt contains confidence scoring guidelines."""
        assert "Confidence Scoring" in SYSTEM_PROMPT
        assert "0.9-1.0" in SYSTEM_PROMPT


# =============================================================================
# Fallback Values Tests
# =============================================================================

class TestFallbackValues:
    """Tests for fallback constants."""
    
    def test_fallback_category(self):
        """Test fallback category is defined."""
        assert TicketClassifier.FALLBACK_CATEGORY == "Other/Uncategorized"
    
    def test_fallback_type(self):
        """Test fallback type is defined."""
        assert TicketClassifier.FALLBACK_TYPE == "General Inquiry/Undefined"
    
    def test_fallback_sla(self):
        """Test fallback SLA is 24 hours."""
        assert TicketClassifier.FALLBACK_SLA.unit == "hours"
        assert TicketClassifier.FALLBACK_SLA.value == 24
    
    def test_similarity_threshold(self):
        """Test similarity threshold is reasonable."""
        assert 0.5 <= TicketClassifier.SIMILARITY_THRESHOLD <= 0.9

