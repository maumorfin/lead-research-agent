from pydantic import BaseModel, Field
from enum import Enum


class CyclingToolType(str, Enum):
    PCS_RANKING = "pcs_ranking"
    PCS_RIDER = "pcs_rider"
    PCS_RACE = "pcs_race"
    PCS_STAGE = "pcs_stage"
    PCS_STARTLIST = "pcs_startlist"
    PCS_RIDER_RESULTS = "pcs_rider_results"
    SEARCH = "search"
    SCRAPE = "scrape"
    FIRECRAWL = "firecrawl"


class ResearchStep(BaseModel):
    step_id: int
    description: str = Field(description="What this step is trying to find out")
    tool: CyclingToolType = Field(description="Which tool to use")
    query: str = Field(description="Slug, URL, or search string — see format per tool in system prompt")


class ResearchPlan(BaseModel):
    question: str = Field(description="The original user question")
    steps: list[ResearchStep] = Field(description="2 to 5 targeted research steps")
