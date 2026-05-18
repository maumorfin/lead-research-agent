from pydantic import BaseModel, Field
from typing import Optional, Literal


class CyclingAnswer(BaseModel):
    question: str = Field(description="The original user question")
    answer: str = Field(description="Main answer in clear prose, 3-6 sentences")
    data_points: list[str] = Field(description="Key facts as short bullet points")
    source_note: Optional[str] = Field(default=None, description="Where the data came from")
    follow_up_suggestions: list[str] = Field(description="2-3 related questions the user might ask next")
    confidence: Literal["high", "medium", "low"] = Field(
        description="high=data is complete and fresh, medium=partial data, low=outdated or missing"
    )
