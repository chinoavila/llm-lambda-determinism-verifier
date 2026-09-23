# Imagen de desarrollo/test para pipeline/ (C-2 orquestador + C-3 baselines, Python).
FROM python:3.12-slim

WORKDIR /workspace/pipeline

COPY pipeline/pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir mypy pytest

COPY pipeline/ ./
RUN pip install --no-cache-dir -e .

CMD ["sh", "-c", "mypy . && pytest"]
