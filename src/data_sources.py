"""
Data source handlers for the Ticket Automation System.

Responsible for retrieving data from external APIs:
- Helpdesk webhook for ticket data
- Service Catalog from external URL
"""

import logging
from typing import Optional

import httpx
import yaml

from .config import APIConfig
from .models import (
    HelpdeskRequest,
    HelpdeskResponse,
    ServiceCatalog,
    ServiceCategory,
    ServiceCatalogRequest,
    SLA,
)


logger = logging.getLogger(__name__)


class DataSourceError(Exception):
    """Base exception for data source errors."""
    pass


class HelpdeskAPIError(DataSourceError):
    """Error when communicating with the Helpdesk API."""
    pass


class ServiceCatalogError(DataSourceError):
    """Error when retrieving the Service Catalog."""
    pass


class HelpdeskClient:
    """
    Client for the IT Helpdesk API.
    
    Retrieves raw helpdesk request data from the configured webhook endpoint.
    """
    
    def __init__(self, config: APIConfig):
        """
        Initialize the Helpdesk client.
        
        Args:
            config: API configuration with endpoint and credentials.
        """
        self._config = config
        self._client: Optional[httpx.Client] = None
    
    def __enter__(self) -> "HelpdeskClient":
        """Context manager entry."""
        self._client = httpx.Client(timeout=self._config.request_timeout)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        if self._client:
            self._client.close()
            self._client = None
    
    def fetch_requests(self) -> list[HelpdeskRequest]:
        """
        Fetch all helpdesk requests from the API.
        
        Returns:
            List of HelpdeskRequest objects.
            
        Raises:
            HelpdeskAPIError: If the API request fails.
        """
        if not self._client:
            raise RuntimeError("Client must be used within a context manager")
        
        payload = {
            "api_key": self._config.helpdesk_api_key,
            "api_secret": self._config.helpdesk_api_secret,
        }
        
        logger.info(f"Fetching helpdesk requests from {self._config.helpdesk_webhook_url}")
        
        try:
            response = self._client.post(
                self._config.helpdesk_webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"Raw API response: {data}")
            
            # Parse response
            helpdesk_response = HelpdeskResponse(**data)
            
            if not helpdesk_response.is_success():
                error_msg = helpdesk_response.message or f"code {helpdesk_response.response_code}"
                if helpdesk_response.response_code == 401:
                    raise HelpdeskAPIError(
                        f"Authentication failed (401): Check HELPDESK_API_KEY and HELPDESK_API_SECRET in .env"
                    )
                raise HelpdeskAPIError(f"API error: {error_msg}")
            
            requests = helpdesk_response.get_requests()
            logger.info(f"Successfully fetched {len(requests)} helpdesk requests")
            
            return requests
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching helpdesk data: {e}")
            raise HelpdeskAPIError(f"HTTP error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error(f"Request error fetching helpdesk data: {e}")
            raise HelpdeskAPIError(f"Request failed: {str(e)}") from e
        except Exception as e:
            logger.error(f"Unexpected error fetching helpdesk data: {e}")
            raise HelpdeskAPIError(f"Unexpected error: {str(e)}") from e


class ServiceCatalogClient:
    """
    Client for retrieving the IT Service Catalog.
    
    Parses the YAML-formatted service catalog from the configured URL.
    """
    
    def __init__(self, config: APIConfig):
        """
        Initialize the Service Catalog client.
        
        Args:
            config: API configuration with catalog URL.
        """
        self._config = config
        self._client: Optional[httpx.Client] = None
    
    def __enter__(self) -> "ServiceCatalogClient":
        """Context manager entry."""
        self._client = httpx.Client(timeout=self._config.request_timeout)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        if self._client:
            self._client.close()
            self._client = None
    
    def fetch_catalog(self) -> ServiceCatalog:
        """
        Fetch and parse the Service Catalog.
        
        Returns:
            ServiceCatalog object with all categories and request types.
            
        Raises:
            ServiceCatalogError: If fetching or parsing fails.
        """
        if not self._client:
            raise RuntimeError("Client must be used within a context manager")
        
        logger.info(f"Fetching service catalog from {self._config.service_catalog_url}")
        
        try:
            response = self._client.get(self._config.service_catalog_url)
            response.raise_for_status()
            
            raw_content = response.text
            logger.debug(f"Raw catalog content length: {len(raw_content)}")
            
            # Parse YAML content
            catalog = self._parse_catalog(raw_content)
            logger.info(
                f"Successfully parsed service catalog with "
                f"{len(catalog.categories)} categories"
            )
            
            return catalog
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching service catalog: {e}")
            raise ServiceCatalogError(f"HTTP error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error(f"Request error fetching service catalog: {e}")
            raise ServiceCatalogError(f"Request failed: {str(e)}") from e
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error: {e}")
            raise ServiceCatalogError(f"Invalid YAML: {str(e)}") from e
        except Exception as e:
            logger.error(f"Unexpected error fetching service catalog: {e}")
            raise ServiceCatalogError(f"Unexpected error: {str(e)}") from e
    
    def _parse_catalog(self, content: str) -> ServiceCatalog:
        """
        Parse YAML content into ServiceCatalog model.
        
        Args:
            content: Raw YAML string from the service catalog endpoint.
            
        Returns:
            Parsed ServiceCatalog object.
        """
        data = yaml.safe_load(content)
        
        # Navigate to categories list
        # Structure: service_catalog.catalog.categories
        categories_data = (
            data.get("service_catalog", {})
            .get("catalog", {})
            .get("categories", [])
        )
        
        categories = []
        for cat_data in categories_data:
            requests = []
            for req_data in cat_data.get("requests", []):
                sla_data = req_data.get("sla", {})
                sla = SLA(
                    unit=sla_data.get("unit", ""),
                    value=sla_data.get("value", 0),
                )
                requests.append(ServiceCatalogRequest(
                    name=req_data.get("name", ""),
                    sla=sla,
                ))
            
            categories.append(ServiceCategory(
                name=cat_data.get("name", ""),
                requests=requests,
            ))
        
        return ServiceCatalog(categories=categories)


def fetch_all_data(config: APIConfig) -> tuple[list[HelpdeskRequest], ServiceCatalog]:
    """
    Convenience function to fetch both helpdesk requests and service catalog.
    
    Args:
        config: API configuration.
        
    Returns:
        Tuple of (requests_list, service_catalog).
        
    Raises:
        DataSourceError: If either fetch operation fails.
    """
    with HelpdeskClient(config) as helpdesk_client:
        requests = helpdesk_client.fetch_requests()
    
    with ServiceCatalogClient(config) as catalog_client:
        catalog = catalog_client.fetch_catalog()
    
    return requests, catalog

