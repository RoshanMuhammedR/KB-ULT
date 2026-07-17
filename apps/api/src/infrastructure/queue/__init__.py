# NOTE: do not re-export the `app` App instance here. The submodule is named
# `app.py`, so binding a package-level `app` name would shadow the submodule for
# attribute-based access (e.g. `import ...queue.app as m; m.app`). The worker loads
# the app via its full dotted path (`src.infrastructure.queue.app.app`), and other
# code imports it from the submodule directly, so no package-level re-export is needed.
from src.infrastructure.queue.procrastinate_queue import ProcrastinateJobQueue

__all__ = ["ProcrastinateJobQueue"]
