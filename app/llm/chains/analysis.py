"""LangChain chains for the AnalysisAgent sub-graph nodes."""
from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.providers import get_llm
from app.services.memory_service import get_memory_manager
from app.tools.instruct import ANALYSIS_INSTRUCTIONS, ANALYSIS_NEW_QUESTION_INSTRUCTIONS

_memory = get_memory_manager()
_llm = get_llm(_memory)
_parser = StrOutputParser()

analysis_chain = ChatPromptTemplate.from_template(
    ANALYSIS_INSTRUCTIONS + "\n\nContext:\n{context}"
) | _llm | _parser

next_step_chain = ChatPromptTemplate.from_template(
    ANALYSIS_NEW_QUESTION_INSTRUCTIONS
    + "\n\nResearch goal: {research_goal}\n\nAnalysis summary: {analysis_summary}"
) | _llm | _parser
