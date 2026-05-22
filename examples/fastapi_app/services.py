from .registries import Session, services


@services.scoped()
class UserService:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def get(self, uid: int) -> dict[str, int | str]:
        return {'id': uid, 'name': 'Ana'}
