from enum import IntEnum
from typing import Literal, List, Optional

from pydantic import BaseModel


class BasicResponse(BaseModel):
    action: Literal["response"]
    success: bool
    message: str


class Error(BaseModel):
    action: Literal["error"]
    message: str


class AuthRequest(BaseModel):
    action: Literal["auth"]
    authenticated: bool
    x: int
    y: int


class AuthConfirmation(BaseModel):
    action: Literal["auth"]
    authenticated: bool


class PrivilegeLevel(IntEnum):
    User = 1
    Admin = 2


class UserData(BaseModel):
    email: str
    password: str
    privilege: PrivilegeLevel


class Interaction(BaseModel):
    user_email: str
    message: str
    timestamp: int


class LoginRequest(BaseModel):
    action: Literal["login"]
    register_user: bool
    email: str
    password: str


class LoginResponse(BaseModel):
    action: Literal["login_response"]
    success: bool
    message: str
    level: Optional[PrivilegeLevel]


class LogoutRequest(BaseModel):
    action: Literal["logout"]


class UploadStart(BaseModel):
    action: Literal["upload_start"]


class UploadFile(BaseModel):
    action: Literal["upload_file"]
    name: str


class UploadResult(BaseModel):
    action: Literal["upload_result"]
    success: bool
    message: str
    path: Optional[str] = None


class UploadEnd(BaseModel):
    action: Literal["upload_end"]


class ViewFilesRequest(BaseModel):
    action: Literal["view_files_request"]
    user_email: str


class ViewFilesResponse(BaseModel):
    action: Literal["view_files_response"]
    success: bool
    message: str
    files: Optional[List[str]] = None


class RemoveFilesRequest(BaseModel):
    action: Literal["remove_files"]
    user_email: str
    files: List[str]


class UserView(BaseModel):
    email: str
    privilege: PrivilegeLevel


class AdminData(BaseModel):
    users: List[UserView]
    interactions: List[Interaction]


class ViewAdminDataRequest(BaseModel):
    action: Literal["view_admin_data_request"]


class ViewAdminDataResponse(BaseModel):
    action: Literal["view_admin_data_response"]
    success: bool
    message: str
    data: Optional[AdminData] = None


class Heartbeat(BaseModel):
    action: Literal["heartbeat"]
