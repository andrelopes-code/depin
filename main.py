from src.di_framework import Container, Scope, enter_request_scope, exit_request_scope, injectable


@injectable(scope=Scope.SINGLETON)
class Repo:
    def __init__(self):
        self.x = 0

    def inc(self):
        self.x += 1
        return self.x


@injectable(scope=Scope.TRANSIENT)
class Service:
    def __init__(self, repo: Repo):
        self.repo = repo

    def do(self):
        return self.repo.inc()


def random_provider():
    import random

    return random.random()


container = Container()

# registra componentes automaticamente
# container.register(Repo, Repo, scope=Scope.SINGLETON)
# container.register(Service, Service, scope=Scope.TRANSIENT)

# registra provider como função
# container.register(float, implementation=random_provider)

print('\n=== Singleton Repo ===')
r1 = container.resolve(Repo)
r2 = container.resolve(Repo)
print(r1 is r2)  # True

print(container.registrations())

# print('\n=== Transient Service ===')
# s1 = container.resolve(Service)
# s2 = container.resolve(Service)
# print(s1 is s2)  # False

# print('\nRepo.x vai aumentando mesmo com services novos:')
# print(s1.do())  # 1
# print(s2.do())  # 2

# print('\n=== Provider customizado ===')
# print(container.resolve(float))
# print(container.resolve(float))  # muda sempre

# print('\n=== Request scope ===')
# # manualmente simulando request
# token = enter_request_scope()
# try:
#     container.register(str, implementation=lambda: 'request-id', scope=Scope.REQUEST)
#     a = container.resolve(str)
#     b = container.resolve(str)
#     print(a, b, a is b)  # mesma instância
# finally:
#     exit_request_scope(token)
