"""
Patches litellm to strip cache_breakpoint from messages before
sending to Groq. Required for crewai 0.28.x + Groq combination.
"""

import litellm
from litellm import completion as _original_completion


def _strip_cache_breakpoint(messages):
    cleaned = []
    for msg in messages:
        m = dict(msg)
        m.pop("cache_breakpoint", None)
        cleaned.append(m)
    return cleaned


def _patched_completion(*args, **kwargs):
    if "messages" in kwargs:
        kwargs["messages"] = _strip_cache_breakpoint(kwargs["messages"])
    elif len(args) >= 2:
        args = list(args)
        args[1] = _strip_cache_breakpoint(args[1])
        args = tuple(args)
    return _original_completion(*args, **kwargs)


litellm.completion = _patched_completion
