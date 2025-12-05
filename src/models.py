"""
Data models for the Ticket Automation System.

Uses Pydantic for robust data validation and serialization.
All models are immutable by default for thread safety.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class SLA(BaseModel):
    """Service Level Agreement specification."""
    
    unit: str = Field(
        default="",
        description="Time unit for SLA (e.g., 'hours', 'days')"
    )
    value: int = Field(
        default=0,
        ge=0,
        description="Numeric value for SLA duration"
    )
    
    model_config = {"frozen": True}
    
    @field_validator("unit")
    @classmethod
    def validate_unit(cls, v: str) -> str:
        """Normalize and validate SLA unit."""
        v = v.lower().strip()
        if v and v not in ("hours", "days", ""):
            # Allow empty string for unclassified, normalize otherwise
            if "hour" in v:
                return "hours"
            elif "day" in v:
                return "days"
        return v
    
    def is_empty(self) -> bool:
        """Check if SLA is not set."""
        return not self.unit or self.value == 0


class HelpdeskRequest(BaseModel):
    """
    Represents a single IT helpdesk request.
    
    Attributes:
        id: Unique identifier for the request
        short_description: Brief summary of the issue
        long_description: Detailed description of the issue
        requester_email: Email of the person who submitted the request
        request_category: Category from Service Catalog (to be filled)
        request_type: Specific type within category (to be filled)
        sla: Service Level Agreement (to be filled)
    """
    
    id: str = Field(..., description="Unique request identifier")
    short_description: str = Field(..., description="Brief issue summary")
    long_description: str = Field(default="", description="Detailed description")
    requester_email: str = Field(..., description="Requester's email")
    request_category: str = Field(default="", description="Service catalog category")
    request_type: str = Field(default="", description="Specific request type")
    sla: SLA = Field(default_factory=SLA, description="Service Level Agreement")
    
    model_config = {"frozen": False}  # Allow modification for classification
    
    def needs_classification(self) -> bool:
        """Check if request needs to be classified."""
        return not self.request_category or not self.request_type or self.sla.is_empty()
    
    def get_full_description(self) -> str:
        """Get combined description for classification."""
        return f"{self.short_description}. {self.long_description}".strip()


class ServiceCatalogRequest(BaseModel):
    """A specific request type within a category."""
    
    name: str = Field(..., description="Request type name")
    sla: SLA = Field(..., description="SLA for this request type")
    
    model_config = {"frozen": True}


class ServiceCategory(BaseModel):
    """A category in the Service Catalog."""
    
    name: str = Field(..., description="Category name")
    requests: list[ServiceCatalogRequest] = Field(
        default_factory=list,
        description="Available request types in this category"
    )
    
    model_config = {"frozen": True}
    
    def get_request_names(self) -> list[str]:
        """Get list of all request type names in this category."""
        return [req.name for req in self.requests]
    
    def find_request(self, name: str) -> Optional[ServiceCatalogRequest]:
        """Find a request type by name (case-insensitive)."""
        name_lower = name.lower()
        for req in self.requests:
            if req.name.lower() == name_lower:
                return req
        return None


class ServiceCatalog(BaseModel):
    """
    Complete IT Service Catalog.
    
    Contains all categories and their associated request types with SLAs.
    """
    
    categories: list[ServiceCategory] = Field(
        default_factory=list,
        description="List of service categories"
    )
    
    model_config = {"frozen": True}
    
    def get_category_names(self) -> list[str]:
        """Get list of all category names."""
        return [cat.name for cat in self.categories]
    
    def find_category(self, name: str) -> Optional[ServiceCategory]:
        """Find a category by name (case-insensitive)."""
        name_lower = name.lower()
        for cat in self.categories:
            if cat.name.lower() == name_lower:
                return cat
        return None
    
    def get_request_type_sla(self, category: str, request_type: str) -> Optional[SLA]:
        """Get SLA for a specific category and request type."""
        cat = self.find_category(category)
        if cat:
            req = cat.find_request(request_type)
            if req:
                return req.sla
        return None
    
    def to_classification_context(self) -> str:
        """
        Generate a text representation of the catalog for LLM context.
        
        Returns:
            Formatted string describing all categories and request types.
        """
        lines = ["IT SERVICE CATALOG:\n"]
        
        for category in self.categories:
            lines.append(f"\n## Category: {category.name}")
            for req in category.requests:
                sla_str = f"{req.sla.value} {req.sla.unit}" if req.sla.value > 0 else "N/A"
                lines.append(f"  - {req.name} (SLA: {sla_str})")
        
        return "\n".join(lines)


class ClassificationResult(BaseModel):
    """
    Result of LLM classification for a single request.
    
    Used as structured output from the LLM.
    """
    
    request_category: str = Field(
        ...,
        description="The most appropriate category from the Service Catalog"
    )
    request_type: str = Field(
        ...,
        description="The specific request type within the category"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Classification confidence (0-1)"
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation for the classification"
    )
    
    model_config = {"frozen": True}


class HelpdeskResponse(BaseModel):
    """Response structure from the helpdesk API."""
    
    response_code: int
    data: Optional[dict] = None
    message: Optional[str] = None
    
    def is_success(self) -> bool:
        """Check if response indicates success."""
        return self.response_code == 200 and self.data is not None
    
    def get_requests(self) -> list[HelpdeskRequest]:
        """Extract list of requests from response."""
        if not self.data:
            return []
        requests_data = self.data.get("requests", [])
        return [HelpdeskRequest(**req) for req in requests_data]

