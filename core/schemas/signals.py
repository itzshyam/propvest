from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class DataSignal(BaseModel):
    name: str = Field(..., description="Signal name, e.g., 'vacancy_rate'")
    value: float = Field(..., description="The numerical value")
    unit: str = Field(..., description="e.g., 'percentage' or 'dollars'")
    source: str = Field(..., description="Where it came from (REA, SQM, ABS)")
    last_updated: datetime = Field(default_factory=datetime.now)
    metadata: Optional[dict] = Field(default={})