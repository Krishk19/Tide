from pydantic import BaseModel, Field, ConfigDict

class TeacherRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=4)
    name: str = Field(..., min_length=2, max_length=100)

class TeacherLoginRequest(BaseModel):
    username: str
    password: str

class TeacherResponse(BaseModel):
    id: int
    username: str
    name: str

    model_config = ConfigDict(from_attributes=True)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    teacher: TeacherResponse
