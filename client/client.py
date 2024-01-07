import logging
import secrets
import time
from dataclasses import dataclass
from threading import Thread
from typing import Callable, Optional, List

from client.client_state import Authenticate, ClientState, ClientStateContext, ClientDataManager, IDLE_STATE
from shared.connection import ConnectionData, log_connection
from shared.network import ClientInterface
from shared.state import EventMessage, create_error_event, EventMessageType


@dataclass
class AuthenticationData:
    private_key: int
    public_key: int
    secret: int


class FileClient:
    SYS_RAND = secrets.SystemRandom()

    def __init__(self, host: str = "127.0.0.1", port: int = 50000) -> None:
        self.host = host
        self.port = port

        self.network = ClientInterface(host, port)
        self.data: Optional[ConnectionData] = None
        self.data_manager = ClientDataManager()
        self.event_handler: Optional[Callable[[EventMessage], None]] = None

        self.running = True
        self.aborted = False
        self.state: ClientState = Authenticate()
        self.next_states: List[ClientState] = []

        self.process_thread = Thread(target=self.process)

    def set_event_handler(self, handler: Callable[[EventMessage], None]) -> None:
        self.event_handler = handler

    def handle_event(self, event: EventMessage) -> None:
        if event.message_type == EventMessageType.Error:
            logging.error(event.message)
        else:
            log_connection(self.data.connection, event.message)

        if self.event_handler is None:
            return
        self.event_handler(event)

    def enqueue_state(self, state: ClientState) -> None:
        self.next_states.append(state)

    def start(self) -> None:
        self.process_thread.start()

    def process(self) -> None:
        try:
            self.data = self.network.start()
        except Exception as err:
            logging.error(err)
            if self.running:
                self.handle_event(create_error_event(
                    f"An error occurred when establishing a connection to {self.host}:{self.port}"
                ))

            return

        context = ClientStateContext(
            network=self.network, data=self.data, send_event=self.handle_event, enqueue_state=self.enqueue_state,
            client_data=self.data_manager
        )

        while self.running:
            time.sleep(0.1)
            if self.data is None:
                continue

            try:
                self.state.run(context)
            except Exception as e:
                logging.error("An error occurred", exc_info=e)
                self.handle_event(create_error_event("An error occurred."))

            next_state: ClientState
            if len(self.next_states) > 0:
                next_state = self.next_states.pop(0)
            else:
                next_state = IDLE_STATE

            self.state = next_state

    def abort(self) -> None:
        self.aborted = True

    def stop(self) -> None:
        self.running = False
        if self.data is not None:
            self.data.connection.input_buffer.put(None)

        self.process_thread.join()
        self.network.stop()
