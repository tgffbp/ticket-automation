"""Tests for data source clients."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.config import APIConfig
from src.data_sources import (
    HelpdeskClient,
    ServiceCatalogClient,
    HelpdeskAPIError,
    ServiceCatalogError,
)
from src.models import ServiceCatalog


class TestHelpdeskClient:
    """Tests for HelpdeskClient."""
    
    @pytest.fixture
    def config(self):
        """Create test API config."""
        return APIConfig(
            helpdesk_webhook_url="https://test.example.com/webhook",
            helpdesk_api_key="test-key",
            helpdesk_api_secret="test-secret",
            service_catalog_url="https://test.example.com/catalog",
            request_timeout=10,
        )
    
    def test_context_manager(self, config):
        """Test client works as context manager."""
        with HelpdeskClient(config) as client:
            assert client._client is not None
        assert client._client is None
    
    def test_fetch_without_context_raises(self, config):
        """Test fetch raises if not in context manager."""
        client = HelpdeskClient(config)
        with pytest.raises(RuntimeError, match="context manager"):
            client.fetch_requests()
    
    @patch("src.data_sources.httpx.Client")
    def test_fetch_success(self, mock_client_class, config):
        """Test successful request fetch."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "response_code": 200,
            "data": {
                "requests": [
                    {
                        "id": "req_001",
                        "short_description": "Test",
                        "long_description": "Test desc",
                        "requester_email": "test@test.com",
                        "request_category": "",
                        "request_type": "",
                        "sla": {"unit": "", "value": 0},
                    }
                ]
            }
        }
        mock_response.raise_for_status = Mock()
        
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = Mock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = Mock(return_value=False)
        
        with HelpdeskClient(config) as client:
            client._client = mock_client
            requests = client.fetch_requests()
        
        assert len(requests) == 1
        assert requests[0].id == "req_001"
    
    @patch("src.data_sources.httpx.Client")
    def test_fetch_auth_error(self, mock_client_class, config):
        """Test authentication error handling."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "response_code": 401,
        }
        mock_response.raise_for_status = Mock()
        
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        
        with HelpdeskClient(config) as client:
            client._client = mock_client
            with pytest.raises(HelpdeskAPIError, match="Authentication failed"):
                client.fetch_requests()


class TestServiceCatalogClient:
    """Tests for ServiceCatalogClient."""
    
    @pytest.fixture
    def config(self):
        """Create test API config."""
        return APIConfig(
            helpdesk_webhook_url="https://test.example.com/webhook",
            helpdesk_api_key="test-key",
            helpdesk_api_secret="test-secret",
            service_catalog_url="https://test.example.com/catalog",
            request_timeout=10,
        )
    
    @pytest.fixture
    def sample_yaml(self):
        """Sample YAML content."""
        return """
service_catalog:
  catalog:
    categories:
      - name: Access Management
        requests:
          - name: Reset forgotten password
            sla:
              unit: hours
              value: 4
      - name: Hardware Support
        requests:
          - name: Laptop Repair
            sla:
              unit: days
              value: 7
"""
    
    @patch("src.data_sources.httpx.Client")
    def test_fetch_catalog_success(self, mock_client_class, config, sample_yaml):
        """Test successful catalog fetch."""
        mock_response = Mock()
        mock_response.text = sample_yaml
        mock_response.raise_for_status = Mock()
        
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        
        with ServiceCatalogClient(config) as client:
            client._client = mock_client
            catalog = client.fetch_catalog()
        
        assert isinstance(catalog, ServiceCatalog)
        assert len(catalog.categories) == 2
        assert catalog.categories[0].name == "Access Management"
    
    def test_context_manager(self, config):
        """Test client works as context manager."""
        with ServiceCatalogClient(config) as client:
            assert client._client is not None
        assert client._client is None

