from pydantic import BaseModel, Field
from typing import List, Optional
from .signals import DataSignal

class Suburb(BaseModel):
    suburb_id: str = Field(..., description="Unique ID: state_postcode_name")
    name: str
    state: str
    postcode: str
    lga_name: str
    population: int
    pop_growth_rate: float
    
    # Tiering logic (Growth Funnel)
    is_tier_1: bool = False
    
    # Optional Price Data
    median_house_price: Optional[float] = None
    
    # The list of verified data points
    signals: List[DataSignal] = []

    class Config:
        from_attributes = True