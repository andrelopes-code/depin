"""Application services, wired from the per-request session and the seeded request."""

from .registries import RequestTrace, Session, services


@services.scoped()
class UserService:
    def __init__(self, session: Session, trace: RequestTrace) -> None:
        self.session = session
        self.trace = trace

    async def get(self, uid: int) -> dict[str, int | str]:
        return {'id': uid, 'name': 'Ana', 'db': self.session.db.url, 'path': self.trace.path}
