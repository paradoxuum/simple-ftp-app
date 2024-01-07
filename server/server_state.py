import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict

from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import ValidationError, BaseModel

from connection import log_connection, Connection
from data import AuthConfirmation, AuthRequest, UploadStart, UploadFile, UploadResult, ViewFilesRequest, \
    ViewFilesResponse, LoginRequest, PrivilegeLevel, UserData, RemoveFilesRequest, LoginResponse, Interaction, \
    BasicResponse, LogoutRequest, UserView, AdminData, ViewAdminDataResponse, ViewAdminDataRequest
from state import StateContext

data_path = Path(__file__).parent / "server_data"
files_path = data_path / "files"
user_file_path = data_path / "users.json"
log_file_path = data_path / "logs.json"


class UserFile(BaseModel):
    users: Dict[str, UserData]


class LogFile(BaseModel):
    interactions: List[Interaction]


class ServerDataManager:
    def __init__(self):
        self._user_data = UserFile(users={})
        self._logs = LogFile(interactions=[])

        # Map of connection IP -> connection Port -> User Email
        self._connected_users: Dict[str, Dict[str, str]] = {}

    def load(self) -> None:
        if user_file_path.exists():
            # Load users
            with open(user_file_path, "r") as f:
                data = json.load(f)
                self._user_data = UserFile.model_validate(data)

        if log_file_path.exists():
            # Load logs
            with open(log_file_path, "r") as f:
                data = json.load(f)
                self._logs = LogFile.model_validate(data)

    def get_user_files(self, email: str) -> Optional[List[Path]]:
        user = self.get_user(email)
        if user is None or not (files_path.exists() and files_path.is_dir()):
            return None

        email_file_path = files_path / email
        if not (email_file_path.exists() and email_file_path.is_dir()):
            return None

        paths: List[Path] = []
        for path in email_file_path.rglob("*"):
            if path.is_dir():
                continue
            paths.append(path)
        return paths

    def get_user(self, email: str) -> Optional[UserData]:
        if not self.is_user(email):
            return None
        return self._user_data.users[email]

    def get_users(self) -> List[UserData]:
        return list(self._user_data.users.values())

    def get_user_count(self) -> int:
        return len(self._user_data.users)

    def get_logs(self) -> List[Interaction]:
        return self._logs.interactions

    def add_log(self, email: str, message: str) -> None:
        interaction = Interaction(user_email=email, message=message, timestamp=int(time.time()))
        self._logs.interactions.append(interaction)

    def add_user(self, email: str, password: str, privilege_level: PrivilegeLevel = PrivilegeLevel.User) -> None:
        if self.is_user(email):
            return
        data = UserData(email=email, password=password, privilege=privilege_level)
        self._user_data.users[email] = data

    def update_user(self, email: str, data: UserData) -> None:
        if not self.is_user(email):
            return
        self._user_data.users[email] = data

    def set_privilege_level(self, email: str, privilege_level: PrivilegeLevel) -> None:
        data = self.get_user(email)
        if data is None:
            return
        data.privilege = privilege_level
        self.update_user(email, data)

    def get_connected_user(self, connection: Connection) -> Optional[UserData]:
        if connection.ip not in self._connected_users:
            return None

        port_str = str(connection.port)
        if port_str not in self._connected_users[connection.ip]:
            return None

        email = self._connected_users[connection.ip][port_str]
        return self.get_user(email)

    def login(self, connection: Connection, email: str, password: str) -> bool:
        user = self.get_user(email)
        if user is None or user.password != password:
            return False

        if connection.ip not in self._connected_users:
            self._connected_users[connection.ip] = {}

        port_str = str(connection.port)
        if port_str in self._connected_users[connection.ip]:
            return False

        self._connected_users[connection.ip][port_str] = email
        return True

    def logout(self, connection: Connection) -> bool:
        if connection.ip not in self._connected_users:
            return False

        port_str = str(connection.port)
        if port_str not in self._connected_users[connection.ip]:
            return False

        del self._connected_users[connection.ip][port_str]
        if len(self._connected_users[connection.ip]) == 0:
            del self._connected_users[connection.ip]
        return True

    def is_user(self, email: str) -> bool:
        return email in self._user_data.users

    def save(self) -> None:
        user_file_path.parent.mkdir(exist_ok=True, parents=True)
        with open(user_file_path, "w") as f:
            json.dump(self._user_data.model_dump(), f)

        log_file_path.parent.mkdir(exist_ok=True, parents=True)
        with open(log_file_path, "w") as f:
            json.dump(self._logs.model_dump(), f)


@dataclass
class ServerStateContext(StateContext):
    server_data: ServerDataManager


@dataclass
class Authenticate:
    def run(self, ctx: StateContext) -> None:
        # Generate public and private keys and send the public key to the client,
        # so it can generate a shared key
        log_connection(ctx.data.connection, "Generating authentication keys")
        public_key = ctx.data.encryption.generate_keys()
        public_numbers = public_key.public_numbers()

        auth_request = AuthRequest(
            action="auth",
            authenticated=False,
            x=public_numbers.x,
            y=public_numbers.y,
        )
        ctx.network.push_message(ctx.data.connection, auth_request.model_dump_json())

        # Wait for the client to send its public key so we can generate shared key using it
        log_connection(ctx.data.connection, "Waiting for client to authenticate")

        msg = ctx.network.get_message(ctx.data.connection)
        if msg is None:
            return
        auth_response = AuthRequest.model_validate_json(msg)

        client_public_numbers = ec.EllipticCurvePublicNumbers(
            auth_response.x, auth_response.y, ec.SECP384R1()
        )
        ctx.data.encryption.exchange_keys(client_public_numbers.public_key())

        # Finally, send a message back to the client indicating that authentication is complete
        log_connection(ctx.data.connection, "Successfully authenticated")

        ctx.network.push_message(
            ctx.data.connection,
            AuthConfirmation(action="auth", authenticated=True).model_dump_json(),
        )
        ctx.data.encryption.set_enabled(True)


@dataclass
class Login:
    register: bool
    email: str
    password: str

    def _login(self, ctx: ServerStateContext) -> LoginResponse:
        user = ctx.server_data.get_user(self.email)
        if user is None:
            return LoginResponse(action="login_response", success=False, message="Account does not exist",
                                 level=None)

        if user.password != self.password:
            return LoginResponse(action="login_response", success=False, message="Incorrect password", level=None)

        if ctx.server_data.get_connected_user(ctx.data.connection):
            return LoginResponse(action="login_response", success=False, message="Already logged in", level=None)

        if not ctx.server_data.login(ctx.data.connection, self.email, self.password):
            return LoginResponse(action="login_response", success=False, message="Failed to login", level=None)

        return LoginResponse(action="login_response", success=True, message="Successfully logged in",
                             level=user.privilege)

    def _register(self, ctx: ServerStateContext) -> LoginResponse:
        if ctx.server_data.is_user(self.email):
            return LoginResponse(action="login_response", success=False, message="Account already exists",
                                 level=None)

        # If this account is the first account registered, make it an admin account
        privilege_level = PrivilegeLevel.Admin if ctx.server_data.get_user_count() == 0 else PrivilegeLevel.User

        ctx.server_data.add_log(self.email, "Account registered")
        ctx.server_data.add_user(self.email, self.password, privilege_level)

        return LoginResponse(action="login_response", success=True, message="Successfully registered account",
                             level=privilege_level)

    def run(self, ctx: ServerStateContext) -> None:
        response: LoginResponse
        if self.register:
            response = self._register(ctx)
        else:
            response = self._login(ctx)

        ctx.network.push_message(ctx.data.connection, response.model_dump_json())


@dataclass
class Logout:
    def run(self, ctx: ServerStateContext) -> None:
        user = ctx.server_data.get_connected_user(ctx.data.connection)
        response: BasicResponse
        if user is None:
            response = BasicResponse(action="response", success=False, message="Not logged in")
        elif ctx.server_data.logout(ctx.data.connection):
            response = BasicResponse(action="response", success=True, message="Successfully logged out")
        else:
            response = BasicResponse(action="response", success=False, message="Failed to logout")

        ctx.network.push_message(ctx.data.connection, response.model_dump_json())


@dataclass
class Upload:
    @staticmethod
    def _upload_file(ctx: StateContext, base_dir: Path, start_msg: UploadFile) -> Optional[UploadResult]:
        file_path = base_dir / start_msg.name
        if file_path.exists():
            return UploadResult(action="upload_result", success=False, message="File already exists", path=None)

        # Indicate to the client that the server is ready to accept file data
        ctx.network.push_message(ctx.data.connection, UploadResult(action="upload_result", success=True,
                                                                   message="Upload ready", path=None).model_dump_json())

        content_msg = ctx.network.get_message_raw(ctx.data.connection)
        if content_msg is None:
            return None

        base_dir.mkdir(exist_ok=True, parents=True)
        with open(file_path, "wb") as f:
            f.write(content_msg)

        return UploadResult(action="upload_result", success=True, message=f"Successfully uploaded {file_path.name}",
                            path="/".join(file_path.relative_to(base_dir).parts))

    def run(self, ctx: ServerStateContext) -> None:
        connected_user = ctx.server_data.get_connected_user(ctx.data.connection)
        if connected_user is None:
            ctx.network.push_message(ctx.data.connection, UploadResult(action="upload_result", success=False,
                                                                       message="Not logged in", path=None)
                                     .model_dump_json())
            return

        logging.info("Start upload")

        end_received = False
        upload_base_dir = files_path / connected_user.email

        while not end_received:
            msg = ctx.network.get_message(ctx.data.connection)
            if msg is None:
                return

            data = json.loads(msg)
            if "action" in data and data["action"] == "upload_end":
                end_received = True
                continue

            file_data = UploadFile.model_validate(data)
            result = self._upload_file(ctx, upload_base_dir, file_data)
            if result is None:
                # If the result is None, the client likely disconnected, so we should break out of this loop
                break
            ctx.server_data.add_log(connected_user.email, f"Uploaded {file_data.name}")
            ctx.network.push_message(ctx.data.connection, result.model_dump_json())

        logging.info("End upload")


@dataclass
class ViewFiles:
    user_email: str

    def run(self, ctx: ServerStateContext) -> None:
        connected_user = ctx.server_data.get_connected_user(ctx.data.connection)
        if connected_user is None:
            ctx.network.push_message(ctx.data.connection, ViewFilesResponse(action="view_files_response", success=False,
                                                                            message="Not logged in",
                                                                            files=None).model_dump_json())
            return

        if connected_user.email != self.user_email and connected_user.privilege < PrivilegeLevel.Admin:
            ctx.network.push_message(ctx.data.connection, ViewFilesResponse(action="view_files_response", success=False,
                                                                            message="Insufficient permission",
                                                                            files=None
                                                                            ).model_dump_json())
            return

        # Get all files in the files directory and generate
        # relative path strings
        email_file_path = files_path / self.user_email
        file_paths = ctx.server_data.get_user_files(self.user_email)

        relative_paths: List[str] = []
        if file_paths is not None:
            for path in file_paths:
                relative_paths.append("/".join(path.relative_to(email_file_path).parts))

        # Respond to the client with the paths
        log_connection(ctx.data.connection, f"Sent file list containing {len(relative_paths)} file(s) to client")
        response = ViewFilesResponse(action="view_files_response", success=True, message="Successfully viewed files",
                                     files=relative_paths)
        ctx.network.push_message(ctx.data.connection, response.model_dump_json())


@dataclass
class RemoveFiles:
    user_email: str
    files: List[str]

    def run(self, ctx: ServerStateContext):
        connected_user = ctx.server_data.get_connected_user(ctx.data.connection)
        if connected_user is None:
            ctx.network.push_message(ctx.data.connection, ViewFilesResponse(action="view_files_response", success=False,
                                                                            message="Not logged in").model_dump_json())
            return

        same_user = connected_user.email == self.user_email
        if not same_user and connected_user.privilege < PrivilegeLevel.Admin:
            ctx.network.push_message(ctx.data.connection, ViewFilesResponse(action="view_files_response", success=False,
                                                                            message="Insufficient permission"
                                                                            ).model_dump_json())
            return

        folder_path = files_path / self.user_email
        if not (folder_path.exists() and folder_path.is_dir()):
            ctx.network.push_message(ctx.data.connection, ViewFilesResponse(action="view_files_response", success=False,
                                                                            message="No user data folder exists"
                                                                            ).model_dump_json())
            return

        removed_count = 0
        for file_name in self.files:
            file_path = folder_path / file_name
            if not file_path.exists():
                continue
            file_path.unlink()
            removed_count += 1

            log_msg: str
            if same_user:
                log_msg = f"Removed {file_name}"
            else:
                log_msg = f"Removed {file_name} from {self.user_email}'s folder"
            ctx.server_data.add_log(connected_user.email, log_msg)

        ctx.network.push_message(ctx.data.connection,
                                 ViewFilesResponse(action="view_files_response", success=False,
                                                   message=f"Successfully removed {removed_count} file(s)"
                                                   ).model_dump_json())


@dataclass
class ViewAdminData:
    def run(self, ctx: ServerStateContext) -> None:
        connected_user = ctx.server_data.get_connected_user(ctx.data.connection)
        if connected_user is None:
            ctx.network.push_message(ctx.data.connection, ViewAdminDataResponse(action="view_admin_data_response",
                                                                                success=False,
                                                                                message="Not logged in",
                                                                                data=None).model_dump_json())
            return

        if connected_user.privilege < PrivilegeLevel.Admin:
            ctx.network.push_message(ctx.data.connection, ViewAdminDataResponse(action="view_admin_data_response",
                                                                                success=False,
                                                                                message="Insufficient permission",
                                                                                data=None).model_dump_json())
            return

        users: List[UserView] = []
        for user in ctx.server_data.get_users():
            users.append(UserView(email=user.email, privilege=user.privilege))

        data = AdminData(users=users, interactions=ctx.server_data.get_logs())
        response = ViewAdminDataResponse(action="view_admin_data_response", success=True,
                                         message="Successfully retrieved data", data=data)
        ctx.network.push_message(ctx.data.connection, response.model_dump_json())


@dataclass
class Idle:
    def run(self, ctx: StateContext) -> None:
        message = ctx.network.get_message(ctx.data.connection)
        if message is None:
            return

        # Switch to upload state if upload request received
        try:
            UploadStart.model_validate_json(message)
            ctx.enqueue_state(Upload())
            return
        except ValidationError:
            pass

        # Switch to file view state if file view request received
        try:
            view_request = ViewFilesRequest.model_validate_json(message)
            ctx.enqueue_state(ViewFiles(view_request.user_email))
            return
        except ValidationError:
            pass

        # Switch to log in state if login request received
        try:
            login_request = LoginRequest.model_validate_json(message)
            ctx.enqueue_state(Login(register=login_request.register_user, email=login_request.email,
                                    password=login_request.password))
            return
        except ValidationError:
            pass

        # Switch to log out state if logout request received
        try:
            LogoutRequest.model_validate_json(message)
            ctx.enqueue_state(Logout())
            return
        except ValidationError:
            pass

        # Switch to remove files state if remove file request received
        try:
            remove_request = RemoveFilesRequest.model_validate_json(message)
            ctx.enqueue_state(RemoveFiles(user_email=remove_request.user_email, files=remove_request.files))
            return
        except ValidationError:
            pass

        # Switch to view admin data state if view admin data request received
        try:
            ViewAdminDataRequest.model_validate_json(message)
            ctx.enqueue_state(ViewAdminData())
            return
        except ValidationError:
            pass

        logging.info("Invalid message received")


IDLE_STATE = Idle()
ServerState = Authenticate | Idle | Login | Logout | Upload | ViewFiles | ViewAdminData
