"""Shared LLM factory for all agents.

Uses the OpenAI API directly. The model can be selected via the
OPENAI_MODEL env var.
"""

import os

from langchain_openai import ChatOpenAI


def get_llm() -> ChatOpenAI:
    """Return a ChatOpenAI client pointed at the OpenAI API."""
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0.2,
    )
