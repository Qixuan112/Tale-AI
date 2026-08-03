"""Context builder package for TaleCore message processing.

Extracted from TaleCore._handle_respond_message to improve modularity and testability.
"""

from .metadata_builder import MetadataBuilder
from .media_recognizer import MediaRecognizer
from .history_provider import HistoryProvider
from .context_builder import ContextBuilder

__all__ = [
    'MetadataBuilder',
    'MediaRecognizer',
    'HistoryProvider',
    'ContextBuilder',
]
