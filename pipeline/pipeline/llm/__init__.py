"""Cliente LLM agnóstico (OpenAI-compatible) con balanceo de modelos. Ver specs/llm-client.md."""

from pipeline.llm.balancer import Balancer, ModelAssignment, NoModelAvailable, build_balancer
from pipeline.llm.client import Attempt, LLMCall, Outcome
from pipeline.llm.config import ConfigError, LLMConfig, MissingCredentials, load_config

__all__ = [
    "Attempt",
    "Balancer",
    "ConfigError",
    "LLMCall",
    "LLMConfig",
    "MissingCredentials",
    "ModelAssignment",
    "NoModelAvailable",
    "Outcome",
    "build_balancer",
    "load_config",
]
