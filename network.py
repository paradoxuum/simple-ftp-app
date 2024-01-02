import socket
from threading import Thread
from typing import Callable, List, Optional

from connection import Connection, ConnectionHandler
from encryption import NetworkEncryption


class NetworkInterface:
    def __init__(self) -> None:
        self.connectionHandler = ConnectionHandler()
        self.encryption = NetworkEncryption()
        self.running = False

    @staticmethod
    def _make_socket() -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock

    def get_message_raw(self, connection: Connection) -> Optional[bytes]:
        return self.connectionHandler.get_message(connection.ip, connection.port)

    def get_message(self, connection: Connection) -> Optional[str]:
        msg = self.get_message_raw(connection)
        if msg is None:
            return None
        return self.encryption.decrypt(msg)

    def push_message_raw(self, connection: Connection, message: bytes) -> None:
        self.connectionHandler.push_message(connection.ip, connection.port, message)

    def push_message(self, connection: Connection, message: str) -> None:
        encrypted_msg = self.encryption.encrypt(message)
        return self.push_message_raw(connection, encrypted_msg)

    def get_connections(self) -> List[Connection]:
        return self.connectionHandler.get_connections()

    def stop(self) -> None:
        self.running = False
        self.connectionHandler.stop()


class ServerInterface(NetworkInterface):
    def __init__(self, ip: str, port: int) -> None:
        super().__init__()
        self.listen_thread: Optional[Thread] = None
        self.ip = ip
        self.port = port

    def start(self, callback: Callable[[Connection], None]) -> None:
        if self.running:
            raise Exception("Server has already been started!")

        self.running = True
        self.socket = self._make_socket()
        self.socket.bind((self.ip, self.port))

        # Create and start new thread to listen for client connections
        listener = Thread(target=self._listen, args=(self.socket, callback))
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
        self, sock: socket.socket, callback: Callable[[Connection], None]
    ) -> None:
        """Begins a loop which will listen for client connections for as
        long as the application is running

        Args:
            sock: The socket to begin listening on
            callback: A callback to execute when a connection is established
        """
        while self.running:
            sock.listen()

            conn, _ = sock.accept()
            if not self.running:
                break
            conn.setblocking(False)

            connection = self.connectionHandler.add_connection(conn)
            callback(connection)


class ClientInterface(NetworkInterface):
    def __init__(self, ip: str, port: int) -> None:
        super().__init__()
        self.ip = ip
        self.port = port

    def start(self) -> Connection:
        if self.running:
            raise Exception("Client has already been started!")

        self.running = True
        self.socket = self._make_socket()
        self.socket.connect((self.ip, self.port))
        return self.connectionHandler.add_connection(self.socket)

