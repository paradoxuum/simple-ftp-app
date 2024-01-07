import socket
from threading import Thread
from typing import Callable, Dict, List, Optional

from connection import Connection, ConnectionData, ConnectionHandler, Role
from encryption import NetworkEncryption


class NetworkInterface:
    def __init__(self, role: Role) -> None:
        self.connection_handler = ConnectionHandler(role)
        self.running = False
        self.socket: Optional[socket.socket] = None

        self.encryption_map: Dict[Connection, NetworkEncryption] = {}

    @staticmethod
    def _make_socket() -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock

    def set_connection_encryption(
            self, connection: Connection, encryption: NetworkEncryption
    ) -> None:
        self.encryption_map[connection] = encryption

    def get_message_raw(self, connection: Connection) -> Optional[bytes]:
        return self.connection_handler.get_message_raw(connection.ip, connection.port)

    def get_message(self, connection: Connection) -> Optional[str]:
        return self.connection_handler.get_message(connection.ip, connection.port)

    def push_message_raw(self, connection: Connection, message: bytes) -> None:
        self.connection_handler.push_message_raw(
            connection.ip, connection.port, message
        )

    def push_message(self, connection: Connection, message: str) -> None:
        self.connection_handler.push_message(connection.ip, connection.port, message)

    def push_request_raw(self, connection: Connection, message: bytes) -> Optional[str]:
        """Pushes a raw message and waits for a response

        Args:
            connection: The connection to push to
            message: The message to push

        Returns:
            The response
        """
        self.connection_handler.push_message_raw(
            connection.ip, connection.port, message
        )
        return self.connection_handler.get_message(connection.ip, connection.port)

    def push_request(self, connection: Connection, message: str) -> Optional[str]:
        """Pushes a message and waits for a response

        Args:
            connection: The connection to push the message to
            message: The message to push

        Returns:
            The response
        """
        self.connection_handler.push_message(connection.ip, connection.port, message)
        return self.connection_handler.get_message(connection.ip, connection.port)

    def get_connections(self) -> List[Connection]:
        return self.connection_handler.get_connections()

    def stop(self) -> None:
        self.running = False
        self.connection_handler.stop()


class ServerInterface(NetworkInterface):
    def __init__(self, ip: str, port: int) -> None:
        super().__init__(Role.Server)
        self.listen_thread: Optional[Thread] = None
        self.ip = ip
        self.port = port

        self.connection_handler.on_disconnect()

    def start(self, on_connect: Callable[[ConnectionData], None],
              on_disconnect: Callable[[ConnectionData], None]) -> None:
        if self.running:
            raise Exception("Server has already been started!")

        self.connection_handler.on_disconnect(on_disconnect)

        self.running = True
        self.socket = self._make_socket()
        self.socket.bind((self.ip, self.port))

        # Create and start new thread to listen for client connections
        listener = Thread(target=self._listen, args=(self.socket, on_connect))
        listener.start()
        self.listen_thread = listener

    def stop(self) -> None:
        super().stop()
        if self.listen_thread is not None:
            stop_socket = self._make_socket()
            stop_socket.connect((self.ip, self.port))
            self.socket.close()

            self.listen_thread.join()

    def _listen(
            self, sock: socket.socket, callback: Callable[[ConnectionData], None]) -> None:
        """Begins a loop which will listen for client connections for as
        long as the application is running

        Args:
            sock: The socket to begin listening on
            callback: A callback to execute when a connection is added
        """
        while self.running:
            sock.listen()

            conn, _ = sock.accept()
            if not self.running:
                break
            conn.setblocking(False)

            connection = self.connection_handler.add_connection(conn)
            callback(connection)


class ClientInterface(NetworkInterface):
    def __init__(self, ip: str, port: int) -> None:
        super().__init__(Role.Client)
        self.ip = ip
        self.port = port

    def start(self) -> ConnectionData:
        if self.running:
            raise Exception("Client has already been started!")

        self.running = True
        self.socket = self._make_socket()
        self.socket.connect((self.ip, self.port))
        return self.connection_handler.add_connection(self.socket)
