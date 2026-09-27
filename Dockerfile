# Imagen del laboratorio, una etapa por componente (ver docs/docker.md).
#   target engine-build -> servicio engine   (C-1, Haskell: build y tests)
#   target pipeline     -> servicio pipeline (C-2/C-3, Python + binario del engine)
#   target sandbox      -> servicio sandbox  (C-3, ejecución aislada de los baselines)
#   target ui           -> servicio ui       (C-4, SPA + API; ui-build compila y testea la SPA)

# --- C-1: engine (Haskell STLC) -------------------------------------------
FROM haskell:9.6-slim AS engine-build

WORKDIR /workspace/engine

# Cachear dependencias antes de copiar el código, para rebuilds rápidos.
COPY engine/engine.cabal ./
RUN cabal update && cabal build --only-dependencies --enable-tests

# El binario solo sale de esta etapa si pasa los tests: un engine roto
# produciría veredictos equivocados en los registros sin que nadie lo note.
# Los tests leen las fixtures compartidas (../contracts/fixtures).
COPY contracts/ /workspace/contracts/
COPY engine/ ./
RUN cabal build --enable-tests \
    && cabal test \
    && cp "$(cabal list-bin engine)" /usr/local/bin/engine

CMD ["cabal", "test"]

# --- C-2/C-3: pipeline (orquestador + baselines, Python) -------------------
FROM python:3.12-slim AS pipeline

# Runtime del binario de GHC.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgmp10 \
    && rm -rf /var/lib/apt/lists/*

# El orquestador lo lanza como subproceso (contracts/README.md §2).
COPY --from=engine-build /usr/local/bin/engine /usr/local/bin/engine

WORKDIR /workspace/pipeline

COPY pipeline/pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir mypy pytest

COPY pipeline/ ./
RUN pip install --no-cache-dir -e .

CMD ["sh", "-c", "mypy . && pytest"]

# --- C-3: sandbox de los baselines (sin red, ver docs/sandbox.md) -----------
FROM python:3.12-slim AS sandbox

# Usuario sin privilegios con el que corre el código del LLM.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin sandbox

# Solo el worker (stdlib): nada del repo más allá de este archivo.
COPY pipeline/pipeline/baselines/sandbox_worker.py /opt/sandbox/worker.py

ENV SANDBOX_IO=/io SANDBOX_WORK=/work PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-I", "/opt/sandbox/worker.py"]

# --- C-4: UI (React + Vite + Tailwind, ver docs/ui.md) ----------------------
FROM node:22-alpine AS ui-build

WORKDIR /workspace/ui

COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-fund --no-audit

# Como el engine: la SPA solo sale de esta etapa si pasa tsc y vitest.
COPY ui/ ./
RUN npm run check && npm run build

# La API corre en la imagen del pipeline (misma CLI, mismo engine, misma cola
# del sandbox) y sirve la SPA compilada.
FROM pipeline AS ui
COPY --from=ui-build /workspace/ui/dist /workspace/ui/dist
CMD ["python", "-m", "pipeline", "serve", "--host", "0.0.0.0", "--port", "8000"]
