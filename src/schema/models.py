from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class CompanyOrigin(str, Enum):
    FINPAY = "FinPay"
    VAULTLY = "Vaultly"
    EXTERNAL = "External"


class StatusEnum(str, Enum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    UNDER_REVIEW = "UNDER_REVIEW"


class TicketSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NodeBase(BaseModel):
    """Base model enforcing namespaced ID and company provenance."""
    id: str = Field(..., description="Globally unique namespaced identifier (e.g. finpay:person:aarav)")
    company_origin: CompanyOrigin = Field(..., description="Tenant origin of the entity")


class Person(NodeBase):
    name: str
    role: str
    department: str
    email: str
    pagerank: float = Field(default=0.0, description="Computed influence score across PRs and incidents")


class Team(NodeBase):
    name: str
    charter: str


class System(NodeBase):
    name: str
    tech: str = Field(..., description="Tech stack (e.g. Go/Redis, Node/Postgres)")
    domain: str = Field(..., description="Business domain (e.g. Authentication, Ledger, KYC)")
    description: str
    tier: str = Field(default="tier-1", description="Service criticality tier")
    repo: Optional[str] = None


class Document(NodeBase):
    title: str
    doc_type: str = Field(..., description="Type of document (e.g. RFC, Postmortem, Runbook, Architecture)")
    url: str
    excerpt: str = Field(..., description="Concise 2-3 sentence excerpt to minimize memory")
    author_id: str


class Ticket(NodeBase):
    title: str
    ticket_type: str = Field(..., description="Incident, Bug, or Task")
    severity: TicketSeverity
    status: str = Field(default="CLOSED")
    resolved_by_id: str
    affects_system_id: str
    external_id: Optional[str] = Field(None, description="External Jira/Slack issue key e.g. FIN-1042")


class Decision(NodeBase):
    summary: str
    date: str
    effective_date: str
    authority_level: str = Field(..., description="E.g., Architecture Committee, CISO, Team Lead")
    status: StatusEnum = Field(default=StatusEnum.ACTIVE)
    source: str = Field(..., description="Citation source e.g. Slack #sec-arch, Notion RFC-42")


class Policy(NodeBase):
    name: str
    domain: str = Field(..., description="Compliance domain (e.g. Retention, Authentication, PII)")
    description: str
    effective_date: str
    authority_level: str
    status: StatusEnum = Field(default=StatusEnum.ACTIVE)
    source: str


class ExternalAPI(BaseModel):
    id: str
    name: str
    category: str
    provider: str
    company_origin: CompanyOrigin = CompanyOrigin.EXTERNAL


class Relationship(BaseModel):
    """Represents a directional relationship between two nodes."""
    source_id: str
    target_id: str
    rel_type: str
    properties: Dict[str, Any] = Field(default_factory=dict)
