from pydantic import BaseModel


class StravaConnectionStartResponse(BaseModel):
    authorization_url: str
