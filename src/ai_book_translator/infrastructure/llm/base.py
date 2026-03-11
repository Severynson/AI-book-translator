"""Backward-compatibility shim.

New code should import LLMClient from infrastructure.llm.client instead.
"""
from .client import LLMClient as LLMProvider

__all__ = ["LLMProvider"]
