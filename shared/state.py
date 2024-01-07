from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from shared.connection import ConnectionData
from shared.network import NetworkInterface


class EventMessageType(Enum):
    Success = 1
    Info = 2
    Error = 3


@dataclass(frozen=True)
class EventMessage:
    message_type: EventMessageType
    message: str


def create_success_event(message: str) -> EventMessage:
    return EventMessage(EventMessageType.Success, message)


def create_info_event(message: str) -> EventMessage:
    return EventMessage(EventMessageType.Info, message)


def create_error_event(message: str) -> EventMessage:
    return EventMessage(EventMessageType.Error, message)


@dataclass
class StateContext:
    network: NetworkInterface
    data: ConnectionData
    send_event: Callable[[EventMessage], None]
    enqueue_state: Callable[[Any], None]
