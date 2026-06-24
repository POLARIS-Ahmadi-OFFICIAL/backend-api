"""LangChain chains for the ExperimentAgent sub-graph nodes."""
from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.providers import get_llm
from app.services.memory_service import get_memory_manager
from app.tools.instruct import EXPERIMENTAL_PLAN_TOT_INSTRUCTIONS

_memory = get_memory_manager()
_llm = get_llm(_memory)
_parser = StrOutputParser()

plan_tot_chain = ChatPromptTemplate.from_template(
    EXPERIMENTAL_PLAN_TOT_INSTRUCTIONS
    + "\n\nQuestion: {clarified_question}\n\nConstraints: {experimental_constraints}"
) | _llm | _parser

worklist_chain = ChatPromptTemplate.from_template(
    "Given this experimental plan, produce a step-by-step worklist as a numbered list.\n\nPlan:\n{plan}"
) | _llm | _parser
