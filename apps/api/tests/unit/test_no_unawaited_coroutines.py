import ast
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

# Callables that legitimately consume a coroutine without an `await` in front of the call.
COROUTINE_CONSUMERS = {
    "gather", "create_task", "ensure_future", "wait_for", "wait", "shield", "run",
}


def _is_async_generator(fn: ast.AsyncFunctionDef) -> bool:
    # An `async def` containing `yield` returns an async generator, which is correctly
    # called without `await` and driven by `async for`.
    nested = {
        node
        for inner in ast.walk(fn)
        if isinstance(inner, (ast.AsyncFunctionDef, ast.FunctionDef)) and inner is not fn
        for node in ast.walk(inner)
    }
    return any(
        isinstance(node, (ast.Yield, ast.YieldFrom))
        for node in ast.walk(fn)
        if node not in nested
    )


def _is_context_manager(fn: ast.AsyncFunctionDef) -> bool:
    for decorator in fn.decorator_list:
        name = decorator.attr if isinstance(decorator, ast.Attribute) else getattr(decorator, "id", "")
        if "contextmanager" in name:
            return True
    return False


class NoUnawaitedCoroutinesTests(unittest.TestCase):
    """Guard against calling an `async def` and forgetting to await it.

    Sync helpers turned `async` during the async conversion kept their old call sites, so
    routes returned a coroutine object instead of a response model and FastAPI raised
    ResponseValidationError at runtime - a 500 on login, reachable only in production because
    nothing here exercised route serialisation. This checks the whole tree instead.

    Scoped to intra-module calls (bare names and `self.<attr>`) so the target definition is
    resolvable with certainty and the check stays free of false positives.
    """

    def test_every_intramodule_coroutine_call_is_awaited(self):
        offenders = []

        for path in sorted(SRC.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

            module_coros, method_coros = set(), set()
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.AsyncFunctionDef) and not _is_async_generator(node) \
                        and not _is_context_manager(node):
                    module_coros.add(node.name)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                for item in node.body:
                    if isinstance(item, ast.AsyncFunctionDef) and not _is_async_generator(item) \
                            and not _is_context_manager(item):
                        method_coros.add(item.name)

            consumed = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Await):
                    consumed.add(id(node.value))
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and node.func.attr in COROUTINE_CONSUMERS:
                    consumed.update(id(arg) for arg in node.args)
                elif isinstance(node, ast.AsyncWith):
                    consumed.update(id(item.context_expr) for item in node.items)
                elif isinstance(node, ast.AsyncFor):
                    consumed.add(id(node.iter))

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or id(node) in consumed:
                    continue
                func = node.func
                if isinstance(func, ast.Name) and func.id in module_coros:
                    target = func.id
                elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) \
                        and func.value.id == "self" and func.attr in method_coros:
                    target = f"self.{func.attr}"
                else:
                    continue
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno} calls {target}() without await")

        self.assertEqual(offenders, [], "un-awaited coroutine call(s):\n  " + "\n  ".join(offenders))


if __name__ == "__main__":
    unittest.main()
