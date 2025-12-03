from di_framework import Container
from services.user_service import UserService

container = Container()
container.auto_scan(['services'])


us1 = container.resolve(UserService)
us2 = container.resolve(UserService)

print(us2 is us1)
print(us2.user_repository.session)
