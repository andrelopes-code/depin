# Resolution semantics

Two things a parameter's annotation can say beyond "give me exactly one `T`":
that `T` is optional, and that the parameter wants every provider registered
for `T`, not just one.

## Optional dependencies

A parameter annotated `T | None` (or `typing.Optional[T]`) is not a missing
dependency. It resolves to the bound provider when one exists, and to `None`
when none does — decided once, at `freeze()`.

```pycon
>>> from depin import Container
>>> class Cache:
...     def get(self) -> str:
...         return 'cached'
>>> class Service:
...     def __init__(self, cache: Cache | None) -> None:
...         self.cache = cache
>>> di = Container().bind(Service).freeze()
>>> di[Service].cache is None
True

```

Binding `Cache` changes nothing about the annotation, only the outcome:

```pycon
>>> di = Container().bind(Cache).bind(Service).freeze()
>>> isinstance(di[Service].cache, Cache)
True

```

An explicit default wins over optionality: depin never replaces a value the
author wrote, so `cache: Cache | None = fallback` keeps `fallback` when `Cache`
is unbound rather than substituting `None` for it.

A union naming two or more providers is still rejected — `Cache | Logger`
names no single key, whether or not `None` is one of the members — because
stripping `None` from it still leaves no single provider to resolve.

## Collections

`Container.collect` gathers several providers under one `list[Element]` key,
in the order given:

```pycon
>>> from typing import Protocol
>>> class Handler(Protocol):
...     def run(self) -> str: ...
>>> class EmailHandler:
...     def run(self) -> str:
...         return 'email'
>>> class SmsHandler:
...     def run(self) -> str:
...         return 'sms'
>>> di = Container().bind(EmailHandler).bind(SmsHandler).collect(Handler, [EmailHandler, SmsHandler]).freeze()
>>> [handler.run() for handler in di.resolve(list[Handler])]
['email', 'sms']

```

`explain()` shows the collection as a node in its own right:

```pycon
>>> print(di.explain(list[Handler]))
list[Handler]  [transient, collection]
  member_0: EmailHandler  [singleton, class]
  member_1: SmsHandler  [singleton, class]

```

The parameters are named `member_0`, `member_1`, and so on — what `explain()`
prints above, and what the `dot()` and `mermaid()` exports write on each edge.

Members stay bound under their own keys. Each keeps its own lifetime, cache
entry, and teardown; the collection node itself is `Scope.TRANSIENT` and
caches nothing, so every resolution returns a fresh list over the same shared
members. An empty collection — `collect(Handler, [])` — is legal and resolves
to `[]`, a plugin point with nothing plugged in being a real state rather than
an error. Because a member is still bound at its own key, registering it
twice by accident still raises `DuplicateProviderError`, exactly as it would
without `collect` in the picture.

A given `(element, tag)` pair can only be declared with one `collect` call:
calling it twice for the same element and tag also raises
`DuplicateProviderError`, so a collection cannot be assembled by contributions
from separately-shipped registries.

## Generic keys

A parameterised generic — `Repo[User]`, a generic `Protocol`, `dict[str, int]` — is a
provider key like any other, distinguished from every other key by equality. The bare
class and a parameterisation are different keys, so binding both is legal and means two
providers:

```pycon
>>> class User: ...
>>> class Order: ...
>>> class Repo[T]:
...     def __init__(self, rows: list[str]) -> None:
...         self.rows = rows
>>> def user_repo() -> Repo[User]:
...     return Repo(['ana'])
>>> def order_repo() -> Repo[Order]:
...     return Repo(['#1'])
>>> di = Container().bind(user_repo).bind(order_repo).freeze()
>>> di.resolve(Repo[User]).rows
['ana']
>>> di.resolve(Repo[Order]).rows
['#1']

```

A generic key works as a parameter annotation the same way any other key does:

```pycon
>>> class UserService:
...     def __init__(self, repo: Repo[User]) -> None:
...         self.repo = repo
>>> di = Container().bind(user_repo).bind(order_repo).bind(UserService).freeze()
>>> di[UserService].repo.rows
['ana']

```

`explain()` renders the parameterisation, the way it prints everywhere else, rather
than falling back to `repr`:

```pycon
>>> print(di.explain(Repo[User]))
Repo[User]  [singleton, function]

```

Matching is by equality, never by assignability: `Repo[User]` does not satisfy a
parameter annotated `Repo[object]`, even though `User` is a subclass of `object`.

A deprecated `typing` alias is rejected at `freeze()`, naming the canonical spelling to
write instead:

```pycon
>>> import typing
>>> Container().alias(typing.List[User], to=User).freeze()  # noqa: UP006
Traceback (most recent call last):
    ...
depin.errors.InvalidProviderError: cannot use typing.List[__main__.User] as a provider key: it is the deprecated typing alias for list[User], and a different object at runtime, so the two would be two keys that print alike. Write list[User] instead, subscripting builtins.list itself.

```
