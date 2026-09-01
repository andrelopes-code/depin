"""Application services, wired from the per-invocation session and the frame's two values."""

from .registries import CommandTrace, Session, services


@services.scoped()
class ReportService:
    def __init__(self, session: Session, trace: CommandTrace) -> None:
        self.session = session
        self.trace = trace

    def summary(self) -> str:
        return (
            f'tenant={self.trace.tenant} '
            f'subcommand={self.trace.subcommand} '
            f'db={self.session.db.url} '
            f'sessions={self.session.db.open_sessions}'
        )
