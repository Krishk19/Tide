from sqlmodel import Field, SQLModel


class Exam(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    duration_s: int
    join_code: str = Field(index=True, unique=True)
    state: str = "lobby"                     # lobby | live | ended
    started_at: float | None = None
    ends_at: float | None = None
    policy_json: str = "{}"


class ExamFile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    exam_id: int = Field(foreign_key="exam.id", index=True)
    set_name: str                            # "A" | "B"
    name: str
    data: bytes


class Seat(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    exam_id: int = Field(foreign_key="exam.id", index=True)
    seat_no: int
    roll: str
    hostname: str = ""
    token_hash: str = Field(default="", index=True)
    set_name: str | None = None
    state: str = "lobby"                     # lobby | ready | blocked | live | offline | submitted
    resume_state: str = ""
    preflight_json: str = "{}"
    last_seen: float = 0.0
    ends_at_override: float | None = None
    fg_app: str = ""
    simulated: bool = False


class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seat_id: int = Field(index=True)
    ts: float
    kind: str
    data_json: str = "{}"


class Flag(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seat_id: int = Field(index=True)
    ts: float
    kind: str
    severity: str
    title: str
    source: str                              # rule | jev | heuristic | server
    label: str | None = None
    confidence: float | None = None
    data_json: str = "{}"
    action: str = "none"
    screenshot: str | None = None
    status: str = "open"                     # open | dismissed | confirmed
    reviewed_at: float | None = None
    ref: str | None = Field(default=None, index=True)


class Snapshot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seat_id: int = Field(index=True)
    ts: float
    path: str
    sha: str
    text: str
    line_count: int


class Submission(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seat_id: int = Field(index=True)
    ts: float
    file_name: str
    auto: bool = False
