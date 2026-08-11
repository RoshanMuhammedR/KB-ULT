# Production image for the API and the ingestion worker — one image, two commands.
#
# Two stages: the builder compiles wheels (docling and friends need a C toolchain), the
# runtime carries only the installed packages, so the shipped layer has no compilers in it.
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install the CPU build of torch BEFORE the project.
#
# docling -> docling-ibm-models -> torch, and torch's linux dependency block is
# unconditional: cuda-toolkit[cublas,cufft,cusolver,...], nvidia-cudnn, nvidia-nccl,
# nvidia-cusparselt and triton, none of them gated on a GPU actually being present. That is
# ~2.7 GB of wheels (cublas alone is 423 MB) unpacking to roughly 5-7 GB, on a 2-vCPU box
# with no GPU that can never execute a line of it. The CPU wheel index serves the same
# torch without any of it.
#
# Pinned, and deliberately so: `docling>=2.110.0` is a floating requirement, so a future
# docling that wants a newer torch would make the project install below resolve torch from
# the DEFAULT index and drag CUDA back in. The pin plus the guard after the project install
# turn that into a loud build failure instead of a silently 6 GB image.
#
# --index-url (not --extra-index-url) on purpose: PyPI must not be reachable for this step,
# or pip is free to pick the CUDA wheel that shares the same version number. The CPU index
# serves torch's own dependencies (filelock, sympy, jinja2, networkx, fsspec, ...) too, so
# nothing needs PyPI here. `==2.13.0` matches the CPU index's `2.13.0+cpu` — a PEP 440 local
# version segment is ignored by ==, so the pin does not need the +cpu suffix.
#
# Its own layer, ahead of the pyproject COPY, so editing dependencies does not re-download
# half a gigabyte of torch.
RUN pip install --prefix=/install \
      --index-url https://download.pytorch.org/whl/cpu \
      torch==2.13.0 torchvision==0.28.0

# Dependencies resolve from pyproject alone, so this layer is cached until it changes.
# PYTHONPATH is what makes pip SEE the torch installed above: pip discovers installed
# distributions on sys.path, and --prefix installs are not on it (same reason the opencv
# uninstall below needs it). Without it pip considers torch missing and reinstalls the
# CUDA build over the top.
COPY pyproject.toml ./
RUN mkdir -p src && touch src/__init__.py \
  && PYTHONPATH=/install/lib/python3.12/site-packages pip install --prefix=/install .

# Regression guard, in the same spirit as the `import cv2` check below: if anything ever
# pulls the CUDA wheels back in, fail HERE rather than shipping an image that needs six
# times the disk it should and still cannot use a GPU.
RUN if ls /install/lib/python3.12/site-packages | grep -qiE '^(nvidia|triton|cuda_)'; then \
      echo "ERROR: CUDA/GPU wheels in the image — torch resolved from the wrong index:" >&2; \
      ls /install/lib/python3.12/site-packages | grep -iE '^(nvidia|triton|cuda_)' >&2; \
      exit 1; \
    fi \
  && PYTHONPATH=/install/lib/python3.12/site-packages python -c "import torch; print('torch', torch.__version__)"

# Swap OpenCV for its headless build.
#
# docling -> rapidocr -> opencv-python, and docling_ibm_models' TableFormer does `import cv2`
# whether or not OCR is enabled. The desktop wheel bundles Qt and links libGL/libxcb/libX11, so
# in a slim container the import dies with "libxcb.so.1: cannot open shared object file" the
# first time a PDF reaches table extraction. Installing those system libraries would work but
# drags in ~205 MB of Mesa drivers to satisfy a library nothing here ever renders with.
# The headless wheel is the same OpenCV without the GUI backends and has no unresolved
# system dependencies at all.
#
# --no-deps because pip would otherwise pull opencv-python straight back in as rapidocr's
# dependency. PYTHONPATH is needed for the uninstall: pip finds distributions on sys.path, and
# --prefix installs are not on it. Consequence: `pip check` reports rapidocr's requirement as
# unsatisfied. That is cosmetic — both packages import the identical `cv2` module.
#
# The import below is the regression guard: this stage shares python:3.12-slim with the runtime
# and adds only compilers, so if a dependency ever drags the GUI wheel back in, the build fails
# here instead of a worker failing on the first upload.
RUN PYTHONPATH=/install/lib/python3.12/site-packages pip uninstall -y opencv-python \
  && pip install --prefix=/install --no-deps opencv-python-headless \
  && PYTHONPATH=/install/lib/python3.12/site-packages python -c "import cv2"


FROM python:3.12-slim AS runtime

# /app MUST come before site-packages. The builder installs the project itself, which
# includes a stub `src` package; a console script like `procrastinate` puts its own bin
# directory on sys.path rather than the cwd, so without /app first that empty stub shadows
# the real source and the worker dies with ModuleNotFoundError on src.infrastructure.
#
# TORCHDYNAMO_DISABLE: docling's models reach torch.compile, whose inductor backend generates
# C++ and shells out to g++ *at inference time*. The runtime stage has no compiler — that is
# the entire point of it — so the first PDF fails with "InvalidCxxCompiler: No working C++
# compiler found in torch._inductor.config.cpp.cxx: (None, 'g++')". Disabling dynamo makes
# torch.compile a no-op and the eager path runs fine. Shipping a compiler instead would trade
# ~200 MB and a JIT compile on a 4 GB shared box for nothing this workload needs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:$PATH" \
    TORCHDYNAMO_DISABLE=1 \
    PYTHONPATH=/app:/install/lib/python3.12/site-packages

# curl is used by the container healthcheck below.
RUN apt-get update \
  && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/* \
  && useradd --create-home --uid 10001 app

COPY --from=builder /install /install

WORKDIR /app
COPY --chown=app:app . .
# Committed from Windows, the exec bit does not survive; set it here rather than relying on
# git's index (belt and braces with .gitattributes).
RUN chmod +x /app/docker-entrypoint.sh

# Docling and tiktoken cache models under $HOME; give them a writable one.
#
# HF_HOME/TORCH_HOME point the model weights at /models, which compose mounts as a named
# volume shared by the api and worker. Left under $HOME they land in the container's
# writable layer instead: destroyed by every `docker compose up -d`, so the first ingestion
# after each deploy re-downloads hundreds of megabytes from HuggingFace, and stored twice
# because the api and worker are separate containers off the same image.
ENV HOME=/home/app \
    HF_HOME=/models \
    TORCH_HOME=/models
RUN mkdir -p /models && chown app:app /models
USER app

EXPOSE 8000

# 127.0.0.1, never localhost: inside a container localhost can resolve to ::1 first, and a
# server bound to IPv4 only then fails every probe while serving traffic perfectly.
#
# 60s, not 15s: every probe writes an access-log line, and at 15s that is ~5,760 lines a day
# per container of pure noise in an unrotated log. retries=5 keeps the same tolerance for a
# genuinely wedged process, and deploy.sh polls health itself on a 5s loop, so rollout speed
# does not depend on this interval.
HEALTHCHECK --interval=60s --timeout=5s --start-period=40s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Invoked through `sh` so it works even when /app is bind-mounted from a host that does not
# carry a Unix exec bit (Windows dev machines).
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
