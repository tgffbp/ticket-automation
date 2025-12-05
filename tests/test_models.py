"""Tests for data models."""

import pytest
from src.models import (
    SLA,
    HelpdeskRequest,
    ServiceCatalog,
    ServiceCategory,
    ServiceCatalogRequest,
    ClassificationResult,
)


class TestSLA:
    """Tests for SLA model."""
    
    def test_empty_sla(self):
        """Test empty SLA detection."""
        sla = SLA(unit="", value=0)
        assert sla.is_empty() is True
        
    def test_valid_sla(self):
        """Test valid SLA."""
        sla = SLA(unit="hours", value=4)
        assert sla.is_empty() is False
        assert sla.unit == "hours"
        assert sla.value == 4
    
    def test_sla_unit_normalization(self):
        """Test that SLA units are normalized."""
        sla = SLA(unit="Hours", value=4)
        assert sla.unit == "hours"


class TestHelpdeskRequest:
    """Tests for HelpdeskRequest model."""
    
    def test_needs_classification_empty(self):
        """Test classification check for empty request."""
        request = HelpdeskRequest(
            id="req_001",
            short_description="Test",
            requester_email="test@example.com",
        )
        assert request.needs_classification() is True
    
    def test_needs_classification_partial(self):
        """Test classification check for partially filled request."""
        request = HelpdeskRequest(
            id="req_001",
            short_description="Test",
            requester_email="test@example.com",
            request_category="Access Management",
        )
        assert request.needs_classification() is True
    
    def test_needs_classification_complete(self):
        """Test classification check for complete request."""
        request = HelpdeskRequest(
            id="req_001",
            short_description="Test",
            requester_email="test@example.com",
            request_category="Access Management",
            request_type="Reset forgotten password",
            sla=SLA(unit="hours", value=4),
        )
        assert request.needs_classification() is False
    
    def test_get_full_description(self):
        """Test full description generation."""
        request = HelpdeskRequest(
            id="req_001",
            short_description="Password reset",
            long_description="I forgot my password",
            requester_email="test@example.com",
        )
        full = request.get_full_description()
        assert "Password reset" in full
        assert "I forgot my password" in full


class TestServiceCatalog:
    """Tests for ServiceCatalog model."""
    
    @pytest.fixture
    def sample_catalog(self):
        """Create a sample catalog for testing."""
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
                            name="MFA Reset",
                            sla=SLA(unit="hours", value=2),
                        ),
                    ],
                ),
                ServiceCategory(
                    name="Hardware Support",
                    requests=[
                        ServiceCatalogRequest(
                            name="Laptop Repair",
                            sla=SLA(unit="days", value=7),
                        ),
                    ],
                ),
            ]
        )
    
    def test_get_category_names(self, sample_catalog):
        """Test category names retrieval."""
        names = sample_catalog.get_category_names()
        assert "Access Management" in names
        assert "Hardware Support" in names
    
    def test_find_category(self, sample_catalog):
        """Test finding category by name."""
        cat = sample_catalog.find_category("access management")
        assert cat is not None
        assert cat.name == "Access Management"
    
    def test_find_category_not_found(self, sample_catalog):
        """Test finding non-existent category."""
        cat = sample_catalog.find_category("nonexistent")
        assert cat is None
    
    def test_get_request_type_sla(self, sample_catalog):
        """Test SLA retrieval."""
        sla = sample_catalog.get_request_type_sla(
            "Access Management",
            "Reset forgotten password",
        )
        assert sla is not None
        assert sla.unit == "hours"
        assert sla.value == 4
    
    def test_to_classification_context(self, sample_catalog):
        """Test context generation for LLM."""
        context = sample_catalog.to_classification_context()
        assert "Access Management" in context
        assert "Reset forgotten password" in context
        assert "4 hours" in context


class TestClassificationResult:
    """Tests for ClassificationResult model."""
    
    def test_valid_result(self):
        """Test valid classification result."""
        result = ClassificationResult(
            request_category="Access Management",
            request_type="Reset forgotten password",
            confidence=0.95,
            reasoning="User mentioned password",
        )
        assert result.request_category == "Access Management"
        assert result.confidence == 0.95
    
    def test_confidence_bounds(self):
        """Test confidence score validation."""
        with pytest.raises(ValueError):
            ClassificationResult(
                request_category="Test",
                request_type="Test",
                confidence=1.5,  # Invalid: > 1.0
            )

