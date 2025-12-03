from di_framework import Container, Scope, enter_request_scope, exit_request_scope, get_request_store
from services.user_repository import UserRepository
from services.user_service import UserService

container = Container()

container.register(implementation=UserRepository, scope=Scope.REQUEST)
container.register(implementation=UserService, scope=Scope.REQUEST)


token = enter_request_scope()

r1 = container.resolve(UserRepository)
r2 = container.resolve(UserRepository)
print(r1 is r2)


s1 = container.resolve(UserService)
s2 = container.resolve(UserService)
print(s1 is s2)

print(get_request_store())

exit_request_scope(token)
print(get_request_store())
