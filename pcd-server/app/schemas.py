from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class FileRecord(BaseModel):
    id: str
    filename: str
    size: int | None = None
    created_at: str
    original_url: Optional[str]
    cleaned_url: Optional[str]
    delta_url: Optional[str]
    summary: Optional[Dict[str, Any]]


class CleanRequest(BaseModel):
    grid: float = Field(0.35)
    q_low: float = Field(0.02)
    q_high: float = Field(0.90)
    smooth_cells: int = Field(7)
    h_min: float = Field(0.20)
    h_max: float = Field(3.0)
    min_len: float = Field(3.0)
    min_width: float = Field(1.4)
    max_width: float = Field(3.5)
    min_elong: float = Field(2.2)
    density_min: int = Field(5)
    use_hough: bool = Field(False)
    hough_theta_step: float = Field(5.0)
    hough_rho_bin: float = Field(0.5)
    hough_topk: int = Field(8)
    hough_min_len: float = Field(8.0)
    hough_min_w: float = Field(1.0)
    hough_max_w: float = Field(4.5)
    hough_dilate: int = Field(1)
    debug_dump: bool = Field(False)


class CleanResponse(BaseModel):
    id: str
    original_url: Optional[str]
    cleaned_url: Optional[str]
    delta_url: Optional[str]
    summary: Optional[Dict[str, Any]]


