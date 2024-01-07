import logging
import secrets
import time
from dataclasses import dataclass
from threading import Thread
from typing import Generic, List, Optional, TypeVar, Dict

from server.server_state import Authenticate, ServerState, IDLE_STATE, ServerDataManager, ServerStateContext
from shared.connection import ConnectionData, log_connection
from shared.network import ServerInterface
from shared.state import EventMessage, EventMessageType


@dataclass
class AuthenticationData:
    private_key: int
    public_key: int
    secret: int


T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    success: bool
    error: Optional[str]
    value: Optional[T]


class ConnectionProcessor:
    def __init__(self, network: ServerInterface, data: ConnectionData, server_data: ServerDataManager) -> None:
        self.network = network
        self.data = data
        self.server_data = server_data

        self.running = False
        self.state: ServerState = Authenticate()
        self.next_states: List[ServerState] = []
        self.process_thread = Thread(target=self._process)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.process_thread.start()

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self.process_thread.join()

    def enqueue_state(self, state: ServerState) -> None:
        self.next_states.append(state)

    def handle_event(self, event: EventMessage) -> None:
        if event.message_type == EventMessageType.Error:
            logging.error(
                f"[{self.data.connection.ip}:{self.data.connection.port}] {event.message}"
            )
            return

        log_connection(self.data.connection, event.message)

    def _process(self) -> None:
        context = ServerStateContext(
            network=self.network, data=self.data, send_event=self.handle_event, enqueue_state=self.enqueue_state,
            server_data=self.server_data
        )

        while self.running:
            time.sleep(0.1)

            try:
                self.state.run(context)
            except Exception as e:
                logging.error("An error occurred", exc_info=e)

            next_state: ServerState
            if len(self.next_states) > 0:
                next_state = self.next_states.pop(0)
            else:
                next_state = IDLE_STATE

            self.state = next_state


class FileServer:
    SYS_RAND = secrets.SystemRandom()

    def __init__(self, host: str = "127.0.0.1", port: int = 50000) -> None:
        self.host = host
        self.port = port

        self.network = ServerInterface(host, port)
        self.processors: List[ConnectionProcessor] = []
        self.processor_map: Dict[str, Dict[str, ConnectionProcessor]] = {}
        self.data = ServerDataManager()
        self.running = True

    def on_connect(self, data: ConnectionData) -> None:
        processor = ConnectionProcessor(self.network, data, self.data)
        self.processor_map[data.connection.ip] = {
            str(data.connection.port): processor
        }
        self.processors.append(processor)
        processor.start()
        log_connection(data.connection, "Connection established")

    def on_disconnect(self, data: ConnectionData) -> None:
        # Stop processor associated with connection
        connection = data.connection
        self.data.logout(connection)
        if connection.ip not in self.processor_map:
            return

        processors = self.processor_map[connection.ip]
        if str(connection.port) not in processors:
            return

        processor = processors[str(connection.port)]
        connection.input_buffer.put(None)
        processor.stop()

        try:
            self.processors.remove(processor)
        except ValueError:
            pass

        del processors[str(connection.port)]
        if len(processors) == 0:
            del self.processor_map[connection.ip]
        log_connection(connection, "Client disconnected")

    def start(self) -> None:
        try:
            self.data.load()
        except Exception as err:
            self.stop()
            logging.error(f"Failed to load server data", exc_info=err)
            return

        try:
            self.network.start(self.on_connect, self.on_disconnect)
            logging.info(f"Started server on {self.host}:{self.port}")
        except Exception as err:
            self.stop()
            logging.error(
                f"An error occurred when starting the server on {self.host}:{self.port}",
                exc_info=err
            )
            return

        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        self.running = False
        self.network.stop()
        self.data.save()
        for processor in self.processors:
            processor.data.connection.input_buffer.put(None)
            processor.stop()
