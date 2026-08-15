from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,SecretStr
class LoginRequest(BaseModel):
 email:str=Field(min_length=3,max_length=320)
 password:SecretStr=Field(min_length=1,max_length=1024)
class RegistrationRequest(BaseModel):
 model_config=ConfigDict(extra="forbid")
 display_name:str=Field(min_length=1,max_length=200)
 email:str=Field(min_length=3,max_length=320)
 password:SecretStr=Field(min_length=12,max_length=1024)
 account_plan:Literal["athlete","coach"]
 timezone:str=Field(min_length=1,max_length=64)
class AuthenticatedUserResponse(BaseModel):
 id:UUID
 email:str
 display_name:str
 authentication_mode:str
 account_plan:str