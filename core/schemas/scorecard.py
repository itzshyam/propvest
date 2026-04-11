from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict

class SuburbScorecard(BaseModel):
    suburb_id: str
    overall_score: float = Field(..., ge=0, le=100)
    
    # Breakdown: how much did each signal contribute?
    component_scores: Dict[str, float]
    
    generated_at: datetime = Field(default_factory=datetime.now)
    is_incomplete: bool = Field(False, description="True if we had to guess missing data")