from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict

class TelemetryEvent(BaseModel):
    student_session_id: int
    type: str = Field(..., pattern="^(focus-lost|focus-regained|fullscreen-exit|paste|connection-lost|reconnected)$")
    metadata: Optional[dict[str, Any]] = None
    ts: Optional[datetime] = None

class FlagResponse(BaseModel):
    id: int
    student_session_id: int
    student_name: Optional[str] = None
    student_identifier: Optional[str] = None
    session_id: Optional[int] = None
    type: str
    metadata: Optional[dict[str, Any]] = None
    ts: datetime
    status: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class FlagStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(open|dismissed|escalated)$")
