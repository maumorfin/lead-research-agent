from pydantic import BaseModel, Field
from enum import Enum


class ToolType(str, Enum):
    SEARCH = "search"
    SCRAPE = "scrape"


class ResearchStep(BaseModel):
    step_id: int
    description: str = Field(description="What this step is trying to find out")
    tool: ToolType = Field(description="Which tool to use for this step")
    query: str = Field(description="The search query or URL to scrape")


class ResearchPlan(BaseModel):
    company_name: str
    steps: list[ResearchStep] = Field(
        description="Ordered list of research steps, between 5 and 8"
    )
