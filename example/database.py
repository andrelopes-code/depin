import rich


class Engine:
    url = '<dburl>'


class Session:
    def __init__(self, engine: Engine, session_id: str) -> None:
        self.session_id = session_id
        self.engine = engine

    async def commit(self):
        rich.print(f'[green bold]SESSION <{self.session_id}> COMMITED[/green bold]')

    async def rollback(self):
        rich.print(f'[yellow bold]SESSION <{self.session_id}> ROLLBACKED[/yellow bold]')
