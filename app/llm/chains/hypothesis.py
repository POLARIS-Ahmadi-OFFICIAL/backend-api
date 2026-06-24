"""LangChain chains for the HypothesisAgent sub-graph nodes."""
from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.providers import get_llm
from app.services.memory_service import get_memory_manager
from app.tools.instruct import (
    CLARIFY_QUESTION_INSTRUCTIONS,
    HYPOTHESIS_SYNTHESIS,
    SOCRATIC_ANSWER_INSTRUCTIONS,
    SOCRATIC_PASS_INSTRUCTIONS,
    TOT_INSTRUCTIONS,
)

_memory = get_memory_manager()
_llm = get_llm(_memory)
_parser = StrOutputParser()

# Each chain takes a dict of template variables and returns a str
clarify_chain = ChatPromptTemplate.from_template(CLARIFY_QUESTION_INSTRUCTIONS + "\n\nQuestion: {question}") | _llm | _parser

socratic_chain = ChatPromptTemplate.from_template(SOCRATIC_PASS_INSTRUCTIONS + "\n\nClarified question: {clarified_question}") | _llm | _parser

answers_chain = ChatPromptTemplate.from_template(SOCRATIC_ANSWER_INSTRUCTIONS + "\n\nQuestion: {clarified_question}\n\nProbing questions:\n{probing_questions}") | _llm | _parser

tot_chain = ChatPromptTemplate.from_template(TOT_INSTRUCTIONS + "\n\nQuestion: {clarified_question}\n\nSocratic reasoning:\n{socratic_answers}") | _llm | _parser

synthesis_chain = ChatPromptTemplate.from_template(HYPOTHESIS_SYNTHESIS + "\n\nChosen option: {chosen_option}\n\nContext: {context}") | _llm | _parser
