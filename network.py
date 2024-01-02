import socket
from threading import Thread
from typing import Callable, List, Optional

from connection import Connection, ConnectionHandler
from encryption import NetworkEncryption


class NetworkInterface:
    def __init__(self) -> None:
        self.listeners: List[Thread] = []
        self.connectionHandler = ConnectionHandler()
        self.encryption = NetworkEncryption()
        self.running = True

    @staticmethod
    def _make_socket() -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock

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
            conn.setblocking(False)

            connection = self.connectionHandler.add_connection(conn)
            callback(connection)

    def start_server(
            self, ip: str, port: int, callback: Callable[[Connection], None]
    ) -> None:
        sock = self._make_socket()
        sock.bind((ip, port))

        # Create and start new thread to listen for client connections
        listener = Thread(target=self._listen, args=(sock, callback))
        listener.start()
        self.listeners.append(listener)

    def start_client(self, ip: str, port: int) -> Connection:
        sock = self._make_socket()
        sock.connect((ip, port))
        return self.connectionHandler.add_connection(sock)

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
        for listener in self.listeners:
            listener.join()
