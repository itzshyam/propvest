from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from .signals import DataSignal


class Suburb(BaseModel):
    suburb_id: str = Field(..., description="Unique ID: state_postcode_name")
    name: str
    state: str
    postcode: str

    # ABS geography identifiers (Geography Trinity)
    sal_code: Optional[str] = None       # ABS SAL code
    sa2_code: Optional[str] = None       # ABS SA2 code (for signal joins)
    sa2_name: Optional[str] = None
    lga_code: Optional[str] = None       # ABS LGA code (for infra joins)
    lga_name: str

    # Population (LGA-level from ABS ERP)
    population: int
    pop_growth_rate: float               # annual % growth at LGA level

    # Growth Funnel
    is_tier_1: bool = False
    scrape_tier: Optional[Literal["Hot", "Warm", "Cold"]] = None

    # Domain scraping
    domain_slug: Optional[str] = None   # e.g. "paddington-qld-4064"

    # Price data (populated by scrapers)
    median_house_price: Optional[float] = None
    data_thin: bool = False             # True if numberSold < 12

    # Verified data points
    signals: List[DataSignal] = []

    class Config:
        from_attributes = True