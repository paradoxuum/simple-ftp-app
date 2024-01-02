import json
from typing import Dict, Any


def create_message(message_type: str, data: Dict[str, Any]) -> str:
    return json.dumps({**data, "type": message_type})


def create_error(message: str) -> str:
    return create_message("error", {"message": message})

