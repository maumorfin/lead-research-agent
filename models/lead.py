from pydantic import BaseModel, Field
from typing import Optional


class KeyPerson(BaseModel):
    name: str
    title: str


class LeadProfile(BaseModel):
    company_name: str
    website: Optional[str] = None
    industry: Optional[str] = None
    description: Optional[str] = None
    employee_count_estimate: Optional[str] = None
    founding_year: Optional[int] = None
    headquarters: Optional[str] = None
    key_people: list[KeyPerson] = Field(default_factory=list)
    recent_news: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    funding_info: Optional[str] = None
    is_hiring: Optional[bool] = None
    qualification_score: float = Field(
        ge=0, le=10, description="Lead quality score from 0 to 10"
    )
    qualification_reasoning: str = Field(
        description="Why this score was assigned"
    )
    talking_points: list[str] = Field(
        default_factory=list,
        description="Specific angles for a first cold outreach message",
    )
