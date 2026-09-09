"""Every route's type annotations must actually resolve to something.

Two routes shipped with `db: Annotated[AsyncSession, Depends(get_db)]` in a module that
never imported `AsyncSession`. Under `from __future__ import annotations` every annotation
is a string, so nothing failed at import: the name was only looked up later, when FastAPI
built the dependency graph, and when the lookup failed it stopped seeing `Depends(get_db)`
and treated `db` as an ordinary query parameter.

The result was a 422 on every call:

    {"type": "missing", "loc": ["query", "db"], "msg": "Field required"}

Filing a source into a second base, and taking it out of its last one, were both dead from
the day they were written. Nothing caught it — not the type checker, not the import, not
the test suite, because no test called those two routes.

This asserts the property rather than the two routes: for every endpoint the app exposes,
the annotations resolve, and no endpoint takes a database session from the query string.
A future route that misspells or forgets an import fails here instead of in production.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import typing
from unittest import TestCase

import src.http.routes as routes_package

#: A parameter with one of these names is always a dependency, never something a caller
#: sends. If one turns up as a query parameter, its `Depends(...)` was lost.
INJECTED_ONLY = {"db", "file_storage", "ingestion_service", "settings"}


def _route_modules():
    for info in pkgutil.iter_modules(routes_package.__path__):
        yield importlib.import_module(f"{routes_package.__name__}.{info.name}")


def _endpoints(module):
    """The functions the module's APIRouter actually serves."""
    router = getattr(module, "router", None)
    if router is None:
        return
    for route in router.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None:
            yield route, endpoint


class RouteAnnotationTests(TestCase):
    def test_every_route_annotation_resolves(self) -> None:
        checked = 0
        for module in _route_modules():
            for route, endpoint in _endpoints(module):
                with self.subTest(module=module.__name__, path=route.path):
                    try:
                        typing.get_type_hints(endpoint, include_extras=True)
                    except NameError as exc:
                        self.fail(
                            f"{module.__name__}{route.path} has an annotation that does not "
                            f"resolve ({exc}). FastAPI drops the Depends() on it and the "
                            f"parameter becomes a required query parameter."
                        )
                    checked += 1

        # A guard on the guard: if the discovery above ever stops finding routes, this test
        # would pass vacuously and go on passing while the thing it protects rots.
        self.assertGreater(checked, 20, "expected to find the app's routes")

    def test_no_route_takes_an_injected_parameter_from_the_query_string(self) -> None:
        for module in _route_modules():
            for route, endpoint in _endpoints(module):
                hints = typing.get_type_hints(endpoint, include_extras=True)
                for name in inspect.signature(endpoint).parameters:
                    if name not in INJECTED_ONLY:
                        continue
                    with self.subTest(module=module.__name__, path=route.path, param=name):
                        annotation = hints.get(name)
                        metadata = getattr(annotation, "__metadata__", ())
                        self.assertTrue(
                            any(hasattr(item, "dependency") for item in metadata),
                            f"{module.__name__}{route.path} takes `{name}` without a "
                            f"Depends(...), so a caller would have to supply it",
                        )
