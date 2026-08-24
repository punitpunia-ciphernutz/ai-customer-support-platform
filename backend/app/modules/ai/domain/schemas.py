from pydantic import BaseModel


class AIRunInput(BaseModel):
    text: str


class AIRunOutput(BaseModel):
    text: str
