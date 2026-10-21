from enum import Enum
from datetime import datetime, timezone
from copy import deepcopy
import uuid


class EventType(Enum):
    BOTAO_APERTADO = {
        "event_id": "",
        "event_type_id": 1,
        "occurred_at": "{datetime}",
        "data": {},
    }

    JOGO_FINALIZADO = {
        "event_id": "",
        "event_type_id": 2,
        "occurred_at": "{datetime}",
        "data": {
            "QtdDePontos": "{QtdDePontos}",
        },
    }

    def generate_payload(self, data: dict | None = None) -> dict:
        payload = deepcopy(self.value)
        event_id = uuid.uuid4()
        payload["event_id"] = str(event_id)
        payload["occurred_at"] = datetime.now(timezone.utc).isoformat()

        if data is not None:
            allowed_fields = payload["data"].keys()
            invalid_fields = data.keys() - allowed_fields

            if invalid_fields:
                raise ValueError(
                    f"Invalid data fields for {self.name}: {invalid_fields}"
                )

            payload["data"].update(data)
        elif payload["data"]:
            allowed_fields = payload["data"].keys()
            raise ValueError(f"Data field must receive values {self.name}: {allowed_fields}")
            return

        return payload
