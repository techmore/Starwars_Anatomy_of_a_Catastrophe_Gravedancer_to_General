"""Fallback stub for when streamlit is not available (headless tests).

Modules that optionally depend on streamlit should import ``st`` from here
instead of catching ``ModuleNotFoundError`` inline.
"""

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - allows headless tests
    class _StreamlitFallback:
        @staticmethod
        def cache_resource(func=None):
            if func is None:
                def decorator(inner):
                    return inner
                return decorator
            return func

        @staticmethod
        def error(*args, **kwargs):
            return None

    st = _StreamlitFallback()
