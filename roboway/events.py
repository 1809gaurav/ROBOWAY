from .models import Event


class EventLog:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, tick: int, event_type: str, msg: str, robot: str | None = None, job: str | None = None, data: dict | None = None) -> Event:
        event = Event(len(self.events) + 1, tick, event_type, robot, job, msg, data or {})
        self.events.append(event)
        return event

    def since(self, event_id: int) -> list[dict]:
        return [event.to_dict() for event in self.events if event.id > event_id]
