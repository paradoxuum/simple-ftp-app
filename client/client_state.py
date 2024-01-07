import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Callable, Tuple

from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import ValidationError

from shared.connection import log_connection
from shared.data import AuthConfirmation, AuthRequest, UploadStart, UploadFile, UploadEnd, UploadResult, \
    ViewFilesRequest, \
    ViewFilesResponse, LoginRequest, BasicResponse, RemoveFilesRequest, UserData, LoginResponse, LogoutRequest, \
    ViewAdminDataRequest, ViewAdminDataResponse, AdminData
from shared.state import StateContext, create_error_event, create_success_event


class ClientDataManager:
    def __init__(self):
        self._logged_in_user: Optional[UserData] = None
        self._files: List[str] = []

        # Tuple of (Email, List of Files)
        self._viewed_files: Optional[Tuple[str, List[str]]] = None
        self._admin_data: Optional[AdminData] = None

        self._user_callback: Optional[Callable[[Optional[UserData]], None]] = None
        self._files_callback: Optional[Callable[[List[str]], None]] = None
        self._admin_data_callback: Optional[Callable[[Optional[AdminData]], None]] = None
        self._viewed_files_callback: Optional[Callable[[Optional[Tuple[str, List[str]]]], None]] = None

    def get_logged_in_user(self) -> Optional[UserData]:
        return self._logged_in_user

    def set_logged_in_user(self, user_data: Optional[UserData]) -> None:
        self._logged_in_user = user_data
        if self._user_callback is not None:
            self._user_callback(user_data)

    def set_admin_data(self, data: Optional[AdminData]):
        self._admin_data = data
        if self._admin_data_callback is not None:
            self._admin_data_callback(data)

    def set_viewed_files(self, email: str, files: List[str]) -> None:
        self._viewed_files = (email, files)
        if self._viewed_files_callback is not None:
            self._viewed_files_callback(self._viewed_files)

    def clear_viewed_files(self) -> None:
        self._viewed_files = None
        if self._viewed_files_callback is not None:
            self._viewed_files_callback(None)

    def on_user_update(self, callback: Callable[[Optional[UserData]], None]) -> None:
        self._user_callback = callback

    def on_files_update(self, callback: Callable[[List[str]], None]) -> None:
        self._files_callback = callback

    def on_admin_data_update(self, callback: Callable[[Optional[AdminData]], None]) -> None:
        self._admin_data_callback = callback

    def on_viewed_files_update(self, callback: Callable[[Optional[Tuple[str, List[str]]]], None]) -> None:
        self._viewed_files_callback = callback

    def set_files(self, files: List[str]) -> None:
        self._files = files
        self._files.sort()
        if self._files_callback is not None:
            self._files_callback(files)

    def add_file(self, file: str) -> None:
        self._files.append(file)
        self._files.sort()
        if self._files_callback is not None:
            self._files_callback(self._files)


@dataclass
class ClientStateContext(StateContext):
    client_data: ClientDataManager


@dataclass
class Authenticate:
    def run(self, ctx: ClientStateContext) -> None:
        # Wait for an authentication request from the server
        log_connection(
            ctx.data.connection, "Waiting for server to generate authentication keys"
        )
        message = ctx.network.get_message(ctx.data.connection)
        if message is None:
            ctx.send_event(create_error_event("Server did not respond"))
            return
        auth_request = AuthRequest.model_validate_json(message)

        # Generate public and private keys, then generate a shared key using the server's public key
        log_connection(ctx.data.connection, "Generating authentication keys")
        server_public_numbers = ec.EllipticCurvePublicNumbers(
            auth_request.x, auth_request.y, ec.SECP384R1()
        )

        public_key = ctx.data.encryption.generate_keys()
        ctx.data.encryption.exchange_keys(server_public_numbers.public_key())

        client_public_numbers = public_key.public_numbers()

        # Send request to the server, so it can generate a shared key from our public key
        auth_response = AuthRequest(
            action="auth",
            authenticated=True,
            x=client_public_numbers.x,
            y=client_public_numbers.y,
        )

        confirm_msg = ctx.network.push_request(
            ctx.data.connection, auth_response.model_dump_json()
        )
        if confirm_msg is None:
            ctx.send_event(create_error_event("Server did not confirm authentication"))
            return
        AuthConfirmation.model_validate_json(confirm_msg)
        ctx.data.encryption.set_enabled(True)
        log_connection(ctx.data.connection, "Successfully authenticated")


@dataclass
class Login:
    register: bool
    email: str
    password: str

    def run(self, ctx: ClientStateContext) -> None:
        request = LoginRequest(action="login", register_user=self.register, email=self.email,
                               password=self.password)
        response_msg = ctx.network.push_request(ctx.data.connection, request.model_dump_json())
        if response_msg is None:
            return

        response = LoginResponse.model_validate_json(response_msg)
        if not response.success:
            ctx.send_event(create_error_event(response.message))
            return

        ctx.send_event(create_success_event(response.message))
        if not self.register:
            data = UserData(email=self.email, password=self.password, privilege=response.level)
            ctx.client_data.set_logged_in_user(data)
            ctx.enqueue_state(ViewFiles(self.email, admin_view=False))
            ctx.enqueue_state(ViewAdminData())


@dataclass
class Logout:
    def run(self, ctx: ClientStateContext) -> None:
        response_msg = ctx.network.push_request(ctx.data.connection, LogoutRequest(action="logout").model_dump_json())
        if response_msg is None:
            return

        response = BasicResponse.model_validate_json(response_msg)
        if response.success:
            ctx.client_data.set_logged_in_user(None)
            ctx.client_data.set_files([])
            ctx.client_data.clear_viewed_files()
            ctx.client_data.set_admin_data(None)
            ctx.send_event(create_success_event(response.message))
        else:
            ctx.send_event(create_error_event(response.message))


@dataclass
class Upload:
    paths: List[Path]

    @staticmethod
    def _check_response(ctx: ClientStateContext, message: str) -> UploadResult:
        response = UploadResult.model_validate_json(message)
        if not response.success:
            ctx.send_event(create_error_event(response.message))
        return response

    @staticmethod
    def _upload(ctx: ClientStateContext, path: Path) -> Optional[UploadResult]:
        start_request = UploadFile(action="upload_file", name=path.name)
        response_msg = ctx.network.push_request(ctx.data.connection, start_request.model_dump_json())

        response = Upload._check_response(ctx, response_msg)
        if not response.success:
            return response

        try:
            with open(path, "rb") as f:
                content = f.read()
        except Exception as e:
            ctx.send_event(create_error_event(f"Failed to read file: {path}"))
            logging.error(e)
            return None

        response_msg = ctx.network.push_request_raw(ctx.data.connection, content)
        return Upload._check_response(ctx, response_msg)

    def run(self, ctx: ClientStateContext) -> None:
        log_connection(ctx.data.connection, "Start uploading")

        request = UploadStart(action="upload_start")
        ctx.network.push_message(ctx.data.connection, request.model_dump_json())

        error_count = 0
        for path in self.paths:
            result = self._upload(ctx, path)
            if result.success:
                if result.path is not None:
                    ctx.client_data.add_file(result.path)
            else:
                error_count += 1

        end_request = UploadEnd(action="upload_end")
        ctx.network.push_message(ctx.data.connection, end_request.model_dump_json())
        log_connection(ctx.data.connection, f"Uploading finished, {error_count} file(s) failed to upload")


@dataclass
class ViewFiles:
    email: str
    admin_view: bool

    def run(self, ctx: ClientStateContext):
        request = ViewFilesRequest(action="view_files_request", user_email=self.email)
        response_msg = ctx.network.push_request(ctx.data.connection, request.model_dump_json())
        if response_msg is None:
            ctx.send_event(create_error_event("Failed to view files"))
            return

        try:
            response = ViewFilesResponse.model_validate_json(response_msg)
        except ValidationError as err:
            logging.error(f"Failed to validate 'view files' response", exc_info=err)
            ctx.send_event(create_error_event("Failed to view files"))
            return

        if not response.success:
            ctx.send_event(create_error_event(response.message))
            return

        if self.admin_view:
            ctx.client_data.set_viewed_files(self.email, response.files)
        else:
            ctx.client_data.set_files(response.files)

        log_connection(ctx.data.connection,
                       f"Received file list containing {len(response.files)} file(s) for user '{self.email}'")


@dataclass
class RemoveFiles:
    user_email: str
    files: List[str]

    def run(self, ctx: ClientStateContext) -> None:
        request = RemoveFilesRequest(action="remove_files", user_email=self.user_email, files=self.files)
        response_msg = ctx.network.push_request(ctx.data.connection, request.model_dump_json())
        if response_msg is None:
            return

        response = BasicResponse.model_validate_json(response_msg)
        if response.success:
            ctx.send_event(create_success_event(response.message))
        else:
            ctx.send_event(create_error_event(response.message))


@dataclass
class ViewAdminData:
    def run(self, ctx: ClientStateContext) -> None:
        response_msg = ctx.network.push_request(ctx.data.connection, ViewAdminDataRequest(
            action="view_admin_data_request"
        ).model_dump_json())
        if response_msg is None:
            return

        response = ViewAdminDataResponse.model_validate_json(response_msg)
        if not response.success:
            ctx.send_event(create_error_event(response.message))
            return
        ctx.client_data.set_admin_data(response.data)
        log_connection(ctx.data.connection, "Received admin data")


@dataclass
class Idle:
    def run(self, _: ClientStateContext) -> None:
        pass


IDLE_STATE = Idle()
ClientState = Authenticate | Idle | Upload | ViewFiles | Login
