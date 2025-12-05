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
        
        Implements graceful handling of:
        - Missing fields (uses defaults)
        - Changed YAML structure (tries multiple paths)
        - Malformed entries (skips with warning)
        
        Args:
            content: Raw YAML string from the service catalog endpoint.
            
        Returns:
            Parsed ServiceCatalog object.
        """
        data = yaml.safe_load(content)
        
        if not data:
            logger.warning("Empty service catalog received, using empty catalog")
            return ServiceCatalog(categories=[])
        
        # Try multiple possible paths for forward compatibility
        categories_data = None
        possible_paths = [
            lambda d: d.get("service_catalog", {}).get("catalog", {}).get("categories", []),
            lambda d: d.get("catalog", {}).get("categories", []),
            lambda d: d.get("categories", []),
            lambda d: d if isinstance(d, list) else [],
        ]
        
        for path_fn in possible_paths:
            try:
                result = path_fn(data)
                if result:
                    categories_data = result
                    break
            except (AttributeError, TypeError):
                continue
        
        if not categories_data:
            logger.warning("Could not find categories in catalog, using empty catalog")
            return ServiceCatalog(categories=[])
        
        categories = []
        seen_category_names: set[str] = set()
        
        for idx, cat_data in enumerate(categories_data):
            try:
                if not isinstance(cat_data, dict):
                    continue
                    
                requests = []
                for req_data in cat_data.get("requests", []):
                    try:
                        if not isinstance(req_data, dict):
                            continue
                        sla_data = req_data.get("sla", {})
                        if not isinstance(sla_data, dict):
                            sla_data = {}
                        sla = SLA(
                            unit=str(sla_data.get("unit", "")),
                            value=int(sla_data.get("value", 0)),
                        )
                        requests.append(ServiceCatalogRequest(
                            name=str(req_data.get("name", "Unknown")),
                            sla=sla,
                        ))
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Skipping malformed request entry: {e}")
                        continue
                
                # Ensure unique category names to prevent dictionary key collisions
                cat_name = str(cat_data.get("name", "")).strip()
                if not cat_name:
                    cat_name = f"Unknown Category {idx + 1}"
                    logger.warning(f"Category at index {idx} has no name, assigned: '{cat_name}'")
                elif cat_name in seen_category_names:
                    original_name = cat_name
                    cat_name = f"{cat_name} ({idx + 1})"
                    logger.warning(f"Duplicate category name '{original_name}', renamed to: '{cat_name}'")
                
                seen_category_names.add(cat_name)
                
                categories.append(ServiceCategory(
                    name=cat_name,
                    requests=requests,
                ))
            except Exception as e:
                logger.warning(f"Skipping malformed category entry: {e}")
                continue
        
        # Log catalog summary for audit trail
        total_types = sum(len(cat.requests) for cat in categories)
        category_names = [cat.name for cat in categories]
        logger.info(
            f"Parsed catalog: {len(categories)} categories, {total_types} request types"
        )
        logger.debug(f"Categories: {category_names}")
        
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

