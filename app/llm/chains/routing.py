"""LangChain chain for WatcherAgent filesystem-event routing."""
from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.providers import get_llm
from app.services.memory_service import get_memory_manager
from app.tools.instruct import WATCHER_ROUTING_INSTRUCTIONS

_memory = get_memory_manager()
_llm = get_llm(_memory)
_parser = StrOutputParser()

watcher_routing_chain = ChatPromptTemplate.from_template(
    WATCHER_ROUTING_INSTRUCTIONS + "\n\nFilesystem event: {event_description}"
) | _llm | _parser
