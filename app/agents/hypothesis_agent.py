from typing import Dict, Any
import os

from app.agents.base import BaseAgent

try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except (ImportError, RuntimeError):
    STREAMLIT_AVAILABLE = False
    st = None
from app.tools.mcp_orchestrator_bridge import sync_hypothesis_outcome, sync_hypothesis_proposal
from app.tools.memory import MemoryManager

# Lazy import socratic module - only import when needed
_socratic_module = None

def _lazy_import_socratic():
    """Lazy import of socratic module to speed up module loading"""
    global _socratic_module
    if _socratic_module is None:
        from app.tools import socratic
        _socratic_module = socratic
    return _socratic_module

class HypothesisAgent(BaseAgent):
    def __init__(self, name, desc, question: str):
        super().__init__("Hypothesis Agent", desc)
        self.question = question
        self.memory = MemoryManager()
        # Don't import socratic here - lazy load when needed

    def confidence(self, payload: Dict[str, Any]) -> float:
        """Return confidence score for hypothesis tasks."""
        # Low confidence by default (hypothesis agent usually needs user input)
        return 0.3

    def initial_process(self, question, experimental_mode=False, experimental_constraints=None):
        socratic = _lazy_import_socratic()

        resolved_api_key = (
            self.memory.get_var("api_key")
            or os.getenv("HUGGINGFACE_API_KEY")
            or os.getenv("HF_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
        )

        if not resolved_api_key:
            raise ValueError("API key not set. Configure it in Settings or set HUGGINGFACE_API_KEY / GEMINI_API_KEY in the environment.")

        if not question or not question.strip():
            raise ValueError("Question is empty. Provide a valid research question.")

        try:
            clarified_question = socratic.clarify_question(question)
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"Error generating clarified question: {e}") from e

        if not clarified_question or not clarified_question.strip():
            raise RuntimeError(
                "LLM returned an empty clarified question. "
                "Check your API key, quota, and network connectivity."
            )

        try:
            socratic_questions = socratic.socratic_pass(clarified_question)
        except Exception as e:
            raise RuntimeError(f"Error generating Socratic questions: {e}") from e

        if not socratic_questions or not socratic_questions.strip():
            raise RuntimeError("LLM returned empty Socratic questions. Please try again.")

        socratic_answers = None
        try:
            socratic_answers = socratic.socratic_answer_questions(clarified_question, socratic_questions)
        except Exception as e:
            raise RuntimeError(f"Error generating Socratic answers: {e}") from e

        if experimental_mode and experimental_constraints:
            thoughts = socratic.tot_generation_experimental_plan(
                socratic_questions, clarified_question, experimental_constraints)
        else:
            thoughts = socratic.tot_generation(socratic_questions, clarified_question, socratic_answers)
            if not thoughts:
                raise RuntimeError("Tree-of-Thought generation returned empty results. Please try again.")

        if len(thoughts) < 3:
            thoughts = list(thoughts) + [""] * (3 - len(thoughts))

        return clarified_question, socratic_questions, thoughts[:3], socratic_answers

    def build_conversation_context(self, prompt_session_id: str = None):
        """ Build full conversation context from all interactions """
        if prompt_session_id is None:
            try:
                prompt_session_id = self.memory.get_var("current_prompt_session_id")
            except Exception:
                prompt_session_id = None
        
        context_parts = []

        # Get initial question
        initial_q = self.memory.view_component("initial_question")
        if initial_q:
            context_parts.append(f"Initial Question: {initial_q}")

        # Get clarified question
        clarified = self.memory.view_component("clarified_question")
        if clarified:
            context_parts.append(f"Clarified Question: {clarified}")

        # Get socratic pass
        socratic_pass = self.memory.view_component("socratic_pass")
        if socratic_pass:
            context_parts.append(f"Socratic Analysis: {socratic_pass}")

        # Get all thoughts
        thought1 = self.memory.view_component("first_thought_1")
        thought2 = self.memory.view_component("second_thought_1")
        thought3 = self.memory.view_component("third_thought_1")
        if thought1 or thought2 or thought3:
            thoughts = [t for t in [thought1, thought2, thought3] if t]
            context_parts.append(f"Initial Thoughts: {'; '.join(thoughts)}")

        # Get all selected options and their responses
        selected_options = []
        for i in self.memory.get_var("interactions", []):
            if i.get("component") == "option_choice":
                selected_options.append(f"Selected: {i.get('message')}")
            elif i.get("component") == "next_step_option_1":
                selected_options.append(f"Option 1: {i.get('message')}")
            elif i.get("component") == "next_step_option_2":
                selected_options.append(f"Option 2: {i.get('message')}")
            elif i.get("component") == "next_step_option_3":
                selected_options.append(f"Option 3: {i.get('message')}")
            elif i.get("component") == "additional_question":
                selected_options.append(f"Additional Question: {i.get('message')}")

        if selected_options:
            context_parts.append(f"Conversation Flow: {'; '.join(selected_options[-10:])}")  # Last 10 interactions

        # Get socratic questions from iterations
        retry_q = self.memory.view_component("retry_thinking_question")
        if retry_q:
            context_parts.append(f"Latest Socratic Question: {retry_q}")

        return "\n\n".join(context_parts) if context_parts else "No previous context available."

    def get_context_for_followup(self):
        """ Get context from previous conversations for follow-up questions """
        if self.memory.get_var("conversation_events", []):
            latest = self.memory.get_latest_history()
            payload = latest.get("payload", {})
            context = f"Previous question: {payload.get('question', '')}\n"
            if payload.get("thoughts"):
                context += f"Previous thoughts: {str(payload['thoughts'])[:200]}...\n"
            if payload.get("hypothesis"):
                context += f"Previous hypothesis: {payload['hypothesis']}\n"
            return context
        return ""

    def _build_negative_hypotheses_context(self) -> str:
        """Build context from past negative hypotheses for model learning."""
        negative = self.memory.get_negative_hypotheses(limit=None)
        if not negative:
            return ""
        parts = [
            "=== Past hypotheses that did not work ===",
            "IMPORTANT: Do NOT repeat these approaches. Your new hypothesis must differ and address why these failed.",
            "",
        ]
        for i, nh in enumerate(negative, 1):
            hyp_preview = (nh.get("hypothesis_text") or "")[:600]
            if len(nh.get("hypothesis_text", "") or "") > 600:
                hyp_preview += "..."
            parts.append(f"[{i}] Status: {nh.get('status', 'unknown')}")
            parts.append(f"    Hypothesis: {hyp_preview}")
            if nh.get("analysis_summary"):
                summary = nh["analysis_summary"][:500] + ("..." if len(nh["analysis_summary"]) > 500 else "")
                parts.append(f"    Why it failed: {summary}")
            parts.append("")
        return "\n".join(parts)

    def generate_hypothesis_with_context(self, socratic_question, next_step_option, previous_option_1,
                                         previous_option_2, conversation_context):
        """ Generate hypothesis with full conversation context """
        try:
            # Include past negative hypotheses so model can learn from them
            negative_ctx = self._build_negative_hypotheses_context()
            full_context = conversation_context
            if negative_ctx:
                full_context = negative_ctx + "\n\n--- Current conversation ---\n\n" + conversation_context
            socratic = _lazy_import_socratic()
            return socratic.hypothesis_synthesis(
                socratic_question,
                next_step_option,
                previous_option_1,
                previous_option_2,
                full_context
            )
        except Exception as e:
            st.error(f"Error generating hypothesis: {str(e)}. Please check your API key and try again.")
            st.stop()

    def run_agent(self, memory) -> Dict[str, Any]:
        if not STREAMLIT_AVAILABLE or st is None:
            return {
                "status": "ready",
                "message": "Use POST /api/v1/agents/hypothesis/chat or /chat/stream for the interactive hypothesis flow.",
                "stage": str(memory.get_var("stage") or "initial"),
                "hypothesis_preview": (memory.view_component("hypothesis") or "")[:500] or None,
            }

        # If stop button is pressed, jump straight to hypothesis
        if memory.get_var("stop_hypothesis") and memory.get_var("stage") != "analysis":
            with st.chat_message("assistant"):
                with st.spinner("Synthesizing hypothesis from current context..."):
                    try:
                        # Extract available data with fallbacks
                        soc_q = self.memory.view_component("retry_thinking_question") or self.memory.view_component(
                            "clarified_question") or "How can we continue exploring this hypothesis?"
                        picked = self.memory.view_component("next_step_option_1") or self.memory.view_component(
                            "first_thought_1") or self.memory.view_component("last_selected_option") or "Selected option"
                        prev1 = self.memory.view_component("next_step_option_2") or self.memory.view_component(
                            "second_thought_1") or self.memory.view_component("last_prev1") or "Previous option 1"
                        prev2 = self.memory.view_component("next_step_option_3") or self.memory.view_component(
                            "third_thought_1") or self.memory.view_component("last_prev2") or "Previous option 2"

                        # Ensure we have valid values
                        if not soc_q or not picked:
                            st.error(
                                "Insufficient context to generate hypothesis. Please go through the conversation flow first.")
                            memory.set_var("stop_hypothesis", False)
                            st.rerun()

                        # Build conversation context (includes past negative hypotheses)
                        context = self.build_conversation_context()
                        negative_ctx = self._build_negative_hypotheses_context()
                        full_context = (negative_ctx + "\n\n--- Current conversation ---\n\n" + context) if negative_ctx else context
                        # Generate hypothesis with conversation context
                        socratic = _lazy_import_socratic()
                        hypothesis = socratic.hypothesis_synthesis(soc_q, picked, prev1, prev2, full_context)

                        # Ensure hypothesis is never None
                        if hypothesis is None or not str(hypothesis).strip():
                            st.error("Error generating hypothesis. Please check your API key and try again.")
                            st.rerun()

                        st.markdown("**Hypothesis:**")
                        st.markdown(hypothesis)
                        
                        # Generate analysis report
                        with st.spinner("Generating analysis report..."):
                            socratic_question_for_analysis = self.memory.view_component("retry_thinking_question") or self.memory.view_component("socratic_pass") or soc_q
                            analysis_rubric = socratic.local_hypothesis_analysis_fallback(hypothesis, socratic_question_for_analysis)
                            
                            if analysis_rubric and str(analysis_rubric).strip():
                                st.markdown("**Analysis Report:**")
                                st.markdown(analysis_rubric)
                                self.memory.insert_interaction("assistant", analysis_rubric, "analysis_rubric", "hypothesis")

                    except Exception as e:
                        st.error(f"Error generating hypothesis: {str(e)}. Please check your API key and try again.")
                        st.rerun()

                st.success("🎉 Hypothesis generation complete (forced stop).")

            self.memory.insert_interaction("assistant", hypothesis, "hypothesis", "hypothesis")
            memory.last_hypothesis = hypothesis
            sync_hypothesis_proposal(self.memory, hypothesis, source="hypothesis_agent_forced")
            memory.set_var("hypothesis_ready", True)
            memory.set_var("stop_hypothesis", False)
            memory.set_var("stage", "analysis")
            st.rerun()

        # Normal stages
        if memory.get_var("stage") == "initial":
            st.write("Welcome to the hypothesis agent! Please enter a question that you would like to explore further.")

            question = st.chat_input("Ask a question...")

            if question:
                # Increment usage metrics on a new hypothesis run
                counts = memory.get_var("agent_usage_counts", {})
                counts["hypothesis"] = counts.get("hypothesis", 0) + 1
                memory.set_var("agent_usage_counts", counts)

                with st.chat_message("user"):
                    st.markdown(question)

                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        cl_question, soc_pass, thoughts_gen, soc_answers = self.initial_process(
                            question)

                        # Safe unpacking - always get exactly 3 items
                        first_thought = thoughts_gen[0] if len(thoughts_gen) > 0 else "Option 1: Continue exploring"
                        second_thought = thoughts_gen[1] if len(thoughts_gen) > 1 else "Option 2: Continue exploring"
                        third_thought = thoughts_gen[2] if len(thoughts_gen) > 2 else "Option 3: Continue exploring"

                        # Validate that thoughts are not empty
                        if not first_thought or not first_thought.strip():
                            first_thought = "Option 1: Continue exploring"
                        if not second_thought or not second_thought.strip():
                            second_thought = "Option 2: Continue exploring"
                        if not third_thought or not third_thought.strip():
                            third_thought = "Option 3: Continue exploring"

                        # Display everything inside the chat messages
                        st.markdown("**Clarified Question:**")
                        st.markdown(cl_question)

                        st.markdown("**Socratic Pass (Probing Questions):**")
                        st.markdown(soc_pass)

                        st.markdown("**Socratic Reasoning (LLM Answers to Its Own Question):**")
                        st.markdown(soc_answers)

                        st.markdown("**Generated Thoughts:**")
                        st.markdown(f"**1.** {first_thought}")
                        st.markdown(f"**2.** {second_thought}")
                        st.markdown(f"**3.** {third_thought}")

                        # Save interactions to both conversation_events and memory.get_var("interactions", [])
                        self.memory.insert_interaction("user", question, "initial_question", "hypothesis")
                        self.memory.insert_interaction("assistant", cl_question, "clarified_question", "hypothesis")
                        self.memory.insert_interaction("assistant", soc_pass, "socratic_pass", "hypothesis")
                        # CRITICAL: Save socratic answers so they persist after rerun
                        if soc_answers and soc_answers.strip():
                            self.memory.insert_interaction("assistant", soc_answers, "socratic_answers", "hypothesis")
                        self.memory.insert_interaction("assistant", first_thought, "first_thought_1", "hypothesis")
                        self.memory.insert_interaction("assistant", second_thought, "second_thought_1", "hypothesis")
                        self.memory.insert_interaction("assistant", third_thought, "third_thought_1", "hypothesis")

                        # Initialize round count if starting hypothesis stage
                        if "hypothesis_round_count" not in st.session_state:
                            memory.set_var("hypothesis_round_count", 0)
                        
                        memory.set_var("stage", "refine")
                        st.rerun()

        elif memory.get_var("stage") == "refine":
            st.write("You are presented with three lines of distinct thoughts. Please choose the option that explores your initial question best.")
            user_choice = st.chat_input("Make a choice 1, 2, or 3...")

            if user_choice:
                if user_choice not in ["1", "2", "3"]:
                    st.warning("Please enter 1, 2, or 3.")
                    st.stop()

                with st.chat_message("user"):
                    st.markdown(user_choice)

                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        if user_choice == "1":
                            picked = self.memory.view_component("first_thought_1")
                            prev1 = self.memory.view_component("second_thought_1")
                            prev2 = self.memory.view_component("third_thought_1")
                        elif user_choice == "2":
                            picked = self.memory.view_component("second_thought_1")
                            prev1 = self.memory.view_component("first_thought_1")
                            prev2 = self.memory.view_component("third_thought_1")
                        else:
                            picked = self.memory.view_component("third_thought_1")
                            prev1 = self.memory.view_component("first_thought_1")
                            prev2 = self.memory.view_component("second_thought_1")

                        # Show brief analysis of the selected option (not a full hypothesis report)
                        # This is just to help the user understand what they selected
                        st.markdown("**Selected Option:**")
                        st.markdown(picked)

                        st.markdown("---")

                        # Lazy import socratic module
                        socratic = _lazy_import_socratic()
                        clarified_question = self.memory.view_component("clarified_question")
                        if not clarified_question:
                            clarified_question = self.memory.view_component("initial_question") or "How can we continue exploring this?"
                        
                        # Build conversation context
                        context = self.build_conversation_context()
                        
                        result = socratic.retry_thinking_deepen_thoughts(
                            picked, prev1, prev2, clarified_question, context
                        )

                        if result is None or len(result) != 2:
                            soc_q = "How can we continue exploring this hypothesis?"
                            options = ["Why is this approach theoretically sound?",
                                       "What are the mechanistic advantages?",
                                       "How does this compare to alternatives?"]
                        else:
                            soc_q, options = result
                            # Ensure options is a list with exactly 3 items, filtering out None/empty
                            if not isinstance(options, list):
                                options = [str(o) for o in options] if options else []
                            # Filter out None, empty strings, and "None" strings
                            options = [opt for opt in options if
                                       opt and str(opt).strip() and str(opt).strip().lower() != "none"]
                            if len(options) < 3:
                                options = list(options) + [""] * (3 - len(options))
                            elif len(options) > 3:
                                options = options[:3]  # Take only first 3
                            # Ensure no None values
                            options = [
                                opt if opt and str(opt).strip() != "None" else f"Option {i + 1}: Continue exploring" for
                                i, opt in enumerate(options)]

                            # Ensure we only display exactly 3 options, and filter out None/empty values
                            valid_options = [opt for opt in options[:3] if
                                             opt and str(opt).strip() and str(opt).strip().lower() != "none"]
                            # Pad to 3 if needed
                            while len(valid_options) < 3:
                                valid_options.append(
                                    f"Option {len(valid_options) + 1}: Continue exploring this line of reasoning")
                            # Take only first 3
                            valid_options = valid_options[:3]

                            st.markdown("**Continuation Question:**")
                            st.markdown(
                                soc_q if soc_q and soc_q != "None" else "How can we continue exploring this hypothesis?")
                            st.markdown("**Next-Step Options:**")
                            for i, opt in enumerate(valid_options, 1):
                                opt_str = str(opt).strip()
                                if opt_str and opt_str.lower() != "none":
                                    st.markdown(f"{i}. {opt_str}")
                                else:
                                    st.markdown(f"{i}. Option {i}: Continue exploring this line of reasoning")

                        self.memory.insert_interaction("user", user_choice, "tot_choice", "hypothesis")
                        self.memory.insert_interaction("assistant", soc_q if soc_q and str(
                            soc_q).strip().lower() != "none" else "How can we continue exploring this hypothesis?",
                                           "retry_thinking_question", "hypothesis")
                        # Ensure we only save 3 options, using valid_options (defined above)
                        valid_options_to_save = valid_options[:3] if len(valid_options) >= 3 else valid_options + [
                            f"Option {len(valid_options) + i + 1}: Continue exploring" for i in
                            range(3 - len(valid_options))]
                        self.memory.insert_interaction("assistant", valid_options_to_save[0] if len(
                            valid_options_to_save) > 0 else "Option 1: Continue exploring", "next_step_option_1", "hypothesis")
                        self.memory.insert_interaction("assistant", valid_options_to_save[1] if len(
                            valid_options_to_save) > 1 else "Option 2: Continue exploring", "next_step_option_2", "hypothesis")
                        self.memory.insert_interaction("assistant", valid_options_to_save[2] if len(
                            valid_options_to_save) > 2 else "Option 3: Continue exploring", "next_step_option_3", "hypothesis")
                        
                        # Transition to hypothesis stage and initialize round count
                        if "hypothesis_round_count" not in st.session_state:
                            memory.set_var("hypothesis_round_count", 0)
                        
                        memory.set_var("stage", "hypothesis")
                        st.rerun()


        elif memory.get_var("stage") == "hypothesis":

            if memory.get_var("experimental_mode"):
                memory.set_var("stage", "refine")
                st.rerun()

            # Check round count and max rounds
            round_count = memory.get_var("hypothesis_round_count", 0)
            max_rounds = memory.get_var("max_hypothesis_rounds", 5)
            
            # If we've reached max rounds, suggest generating hypothesis
            if round_count >= max_rounds:
                st.warning(f"⚠️ Maximum exploration rounds ({max_rounds}) reached. Consider generating your hypothesis now.")
                if st.button("Generate Hypothesis Now", type="primary", use_container_width=True):
                    memory.set_var("stop_hypothesis", True)
                    st.rerun()

            st.write("**Standard Hypothesis Agent - Iterative Refinement Mode**")
            st.write("You can:")
            st.write("1. **Choose an option (1, 2, or 3)** → generates 3 new continuation options")
            st.write("2. **Ask an additional question** → triggers socratic questioning and TOT thinking")
            st.write("3. **Click 'Generate Hypothesis'** → synthesizes your hypothesis from all conversation")
            st.write(f"**Current Round:** {round_count}/{max_rounds}")

            # Load current options
            opt1 = self.memory.view_component("next_step_option_1")
            opt2 = self.memory.view_component("next_step_option_2")
            opt3 = self.memory.view_component("next_step_option_3")

            with st.expander("Current Next-Step Options", expanded=True):
                st.markdown(f"**1.** {opt1}")
                st.markdown(f"**2.** {opt2}")
                st.markdown(f"**3.** {opt3}")

            # Unified input
            user_input = st.chat_input("Pick option 1, 2, or 3, or ask an additional question...")

            # Additional question (explicit)
            with st.expander("💬 Ask Additional Question", expanded=False):
                additional_question = st.text_input(
                    "Ask a question to refine your thinking:",
                    key="additional_question_input"
                )

                if st.button("Ask Question"):
                    if additional_question.strip():
                        memory.pending_additional_question = additional_question
                        st.rerun()

            # Option selection
            if user_input in ["1", "2", "3"]:
                # Increment round count
                round_count = memory.get_var("hypothesis_round_count", 0)
                max_rounds = memory.get_var("max_hypothesis_rounds", 5)
                
                # Check if we've exceeded max rounds
                if round_count >= max_rounds:
                    st.warning(f"Maximum rounds ({max_rounds}) reached. Generating hypothesis automatically...")
                    memory.set_var("stop_hypothesis", True)
                    st.rerun()
                
                picked = {"1": opt1, "2": opt2, "3": opt3}[user_input]
                prev = [opt1, opt2, opt3]
                prev.remove(picked)

                self.memory.insert_interaction("user", user_input, "option_choice", "hypothesis")
                self.memory.insert_interaction("assistant", picked, "last_selected_option", "hypothesis")
                self.memory.insert_interaction("assistant", prev[0], "last_prev1", "hypothesis")
                self.memory.insert_interaction("assistant", prev[1], "last_prev2", "hypothesis")

                with st.chat_message("assistant"):
                    with st.spinner("Generating continuation options..."):
                        socratic = _lazy_import_socratic()
                        context = self.build_conversation_context()
                        
                        # Check if hypothesis is ready using LLM
                        clarified_q = self.memory.view_component("clarified_question") or ""
                        socratic_q = self.memory.view_component("socratic_pass") or ""
                        previous_opts = f"{prev[0]}; {prev[1]}"
                        
                        # Import instruction for readiness check
                        from app.tools.instruct import HYPOTHESIS_READINESS_CHECK
                        readiness_prompt = HYPOTHESIS_READINESS_CHECK.format(
                            clarified_question=clarified_q[:500],
                            socratic_questions=socratic_q[:500],
                            round_count=round_count + 1,
                            selected_option=picked[:300],
                            previous_options=previous_opts[:300]
                        )
                        
                        try:
                            readiness_response = socratic.generate_text_with_llm(readiness_prompt).strip().upper()
                            is_ready = "READY" in readiness_response
                        except Exception as e:
                            # If LLM check fails, use round count as fallback
                            is_ready = (round_count + 1) >= max_rounds
                        
                        # If ready, generate hypothesis instead of new options
                        if is_ready:
                            st.info("🤖 LLM determined sufficient information gathered. Generating hypothesis...")
                            memory.set_var("stop_hypothesis", True)
                            st.rerun()
                        
                        _, new_opts = socratic.retry_thinking_deepen_thoughts(
                            picked, prev[0], prev[1],
                            self.memory.view_component("clarified_question"),
                            context
                        )

                        for i, opt in enumerate(new_opts[:3], 1):
                            self.memory.insert_interaction("assistant", opt, f"next_step_option_{i}", "hypothesis")
                            st.markdown(f"**{i}.** {opt}")

                # Increment round count
                memory.set_var("hypothesis_round_count", round_count + 1)
                memory.set_var("stage", "hypothesis")
                st.rerun()

            # Additional question flow
            if memory.get_var("pending_additional_question"):
                q = memory.pop("pending_additional_question")
                with st.chat_message("user"):
                    st.markdown(q)

                socratic = _lazy_import_socratic()
                context = self.build_conversation_context()
                clarified = socratic.clarify_question(q)
                questions = socratic.socratic_pass(clarified)
                thoughts = socratic.tot_generation(questions, clarified)

                self.memory.insert_interaction("assistant", clarified, "clarified_question", "hypothesis")
                self.memory.insert_interaction("assistant", questions, "socratic_pass", "hypothesis")

                for i, t in enumerate(thoughts[:3], 1):
                    self.memory.insert_interaction("assistant", t, f"next_step_option_{i}", "hypothesis")

                memory.set_var("stage", "hypothesis")
                st.rerun()

            # Generate final hypothesis

            if st.button("Generate Hypothesis", type="primary", use_container_width=True):
                socratic = _lazy_import_socratic()
                context = self.build_conversation_context()
                
                # Get the selected option and previous options
                socratic_q = self.memory.view_component("retry_thinking_question") or self.memory.view_component("socratic_pass") or "How can we test this hypothesis?"
                selected_option = self.memory.view_component("last_selected_option") or opt1
                prev1 = self.memory.view_component("last_prev1") or opt2
                prev2 = self.memory.view_component("last_prev2") or opt3
                
                # If no selected option, use the first option
                if not selected_option or selected_option == opt1:
                    selected_option = opt1
                    prev1 = opt2
                    prev2 = opt3
                
                with st.chat_message("assistant"):
                    with st.spinner("Synthesizing hypothesis from conversation..."):
                        hypothesis = self.generate_hypothesis_with_context(
                            socratic_q,
                            selected_option,
                            prev1,
                            prev2,
                            context
                        )

                        if not hypothesis or not str(hypothesis).strip():
                            st.error("Error generating hypothesis. Please check your API key and try again.")
                            st.stop()

                        st.markdown("**Hypothesis:**")
                        st.markdown(hypothesis)
                        
                        # Generate analysis report
                        with st.spinner("Generating analysis report..."):
                            socratic_question_for_analysis = self.memory.view_component("retry_thinking_question") or self.memory.view_component("socratic_pass") or socratic_q
                            analysis_rubric = socratic.local_hypothesis_analysis_fallback(hypothesis, socratic_question_for_analysis)
                            
                            if analysis_rubric and str(analysis_rubric).strip():
                                st.markdown("**Analysis Report:**")
                                st.markdown(analysis_rubric)
                                self.memory.insert_interaction("assistant", analysis_rubric, "analysis_rubric", "hypothesis")

                self.memory.insert_interaction("assistant", hypothesis, "hypothesis", "hypothesis")
                memory.last_hypothesis = hypothesis
                sync_hypothesis_proposal(self.memory, hypothesis, source="hypothesis_agent")
                memory.set_var("hypothesis_ready", True)
                memory.set_var("stage", "analysis")
                st.rerun()

        elif memory.get_var("stage") == "analysis":
            # Transitions to Experiment agent
            if st.button("Generate Experimental Plan"):
                memory.set_var("next_agent", "experiment")
                st.rerun()

            # Experimental mode should never reach analysis
            if memory.get_var("experimental_mode"):
                memory.set_var("stage", "experimental_outputs")
                st.rerun()

            socratic = _lazy_import_socratic()
            hypothesis = self.memory.view_component("hypothesis")
            socratic_question = (
                    self.memory.view_component("retry_thinking_question")
                    or self.memory.view_component("socratic_pass")
                    or ""
            )

            if not hypothesis:
                st.error("No hypothesis found. Please generate a hypothesis first.")
                memory.set_var("stage", "hypothesis")
                st.rerun()

            with st.chat_message("assistant"):
                with st.spinner("Analyzing Hypothesis and Producing Report..."):
                    analysis_rubric = socratic.local_hypothesis_analysis_fallback(
                        hypothesis, socratic_question)

                    if not analysis_rubric or not str(analysis_rubric).strip():
                        analysis_rubric = (
                            "Analysis generated but content is empty. "
                            "Please check your API key and try again.")

                st.markdown(analysis_rubric)

            self.memory.insert_interaction("assistant", analysis_rubric, "analysis_rubric", "hypothesis")
            st.success("Analysis complete!")

            # Manual input: Mark current hypothesis as did not work
            with st.expander("📝 Mark as did not work", expanded=False):
                st.caption("Record this hypothesis so the model can learn from it and avoid similar mistakes.")
                reason = st.text_area(
                    "Why it didn't work (optional):",
                    placeholder="e.g., Experimental data contradicted the predictions...",
                    key="negative_hyp_reason",
                )
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("Save as rejected", use_container_width=True, key="mark_rejected"):
                        self.memory.add_negative_hypothesis(
                            hypothesis_text=hypothesis[:4000],
                            status="rejected",
                            research_question=socratic_question or "",
                            analysis_summary=reason[:2000] if reason else "Manually marked as rejected.",
                        )
                        self.memory.add_hypothesis_outcome(
                            hypothesis_text=hypothesis[:4000],
                            status="rejected",
                            evidence_summary=reason[:2000] if reason else "Manually marked as rejected.",
                            source="hypothesis_agent_manual",
                        )
                        sync_hypothesis_outcome(
                            self.memory,
                            hypothesis_text=hypothesis[:4000],
                            status="rejected",
                            evidence_summary=reason[:2000] if reason else "Manually marked as rejected.",
                            source="hypothesis_agent_manual",
                        )
                        st.success("Saved. The model will learn from this.")
                        st.rerun()
                with col_b:
                    if st.button("Save as needs revision", use_container_width=True, key="mark_needs_revision"):
                        self.memory.add_negative_hypothesis(
                            hypothesis_text=hypothesis[:4000],
                            status="needs_revision",
                            research_question=socratic_question or "",
                            analysis_summary=reason[:2000] if reason else "Manually marked as needs revision.",
                        )
                        self.memory.add_hypothesis_outcome(
                            hypothesis_text=hypothesis[:4000],
                            status="needs_revision",
                            evidence_summary=reason[:2000] if reason else "Manually marked as needs revision.",
                            source="hypothesis_agent_manual",
                        )
                        sync_hypothesis_outcome(
                            self.memory,
                            hypothesis_text=hypothesis[:4000],
                            status="needs_revision",
                            evidence_summary=reason[:2000] if reason else "Manually marked as needs revision.",
                            source="hypothesis_agent_manual",
                        )
                        st.success("Saved. The model will learn from this.")
                        st.rerun()

        elif memory.get_var("stage") == "followup":

            st.header("Follow-up Question")

            # Show previous context
            if memory.get_var("conversation_history", []):
                latest = memory.get_var("conversation_history", [])[-1]
                with st.expander("Previous Conversation Context", expanded=True):
                    st.markdown(f"**Previous Question:** {latest['question']}")
                    if latest.get("hypothesis"):
                        hyp = latest["hypothesis"]
                        st.markdown(
                            f"**Previous Hypothesis:** {hyp[:300]}..."
                            if len(hyp) > 300 else f"**Previous Hypothesis:** {hyp}"
                        )

            followup_question = st.text_input(
                "Ask a follow-up question based on the previous hypothesis:",
                placeholder="e.g., 'What experimental methods would validate this hypothesis?'"
            )

            if st.button("🚀 Process Follow-up", type="primary"):
                if not followup_question.strip():
                    st.warning("Please enter a follow-up question.")
                    st.stop()

                socratic = _lazy_import_socratic()
                context = self.get_context_for_followup()
                contextual_question = f"{context}\n\nFollow-up question: {followup_question}"

                with st.spinner("Processing follow-up question..."):
                    clarified = socratic.clarify_question(contextual_question)
                    questions = socratic.socratic_pass(clarified)
                    answers = socratic.socratic_answer_questions(clarified, questions)
                    thoughts = socratic.tot_generation(questions, clarified, answers)

                    thoughts = (thoughts or [])[:3]
                    while len(thoughts) < 3:
                        thoughts.append("")

                # Display
                with st.chat_message("user"):
                    st.markdown(followup_question)

                with st.chat_message("assistant"):
                    st.markdown("**Clarified Question:**")
                    st.markdown(clarified)

                    st.markdown("**Socratic Pass:**")
                    st.markdown(questions)

                    if answers:
                        st.markdown("**Socratic Reasoning:**")
                        st.markdown(answers)

                    st.markdown("**Generated Thoughts:**")
                    for t in thoughts:
                        st.markdown(t)

                # Persist
                self.memory.insert_interaction("user", followup_question, "original_question", "hypothesis")
                self.memory.insert_interaction("assistant", clarified, "clarified_question", "hypothesis")
                self.memory.insert_interaction("assistant", questions, "socratic_pass", "hypothesis")
                if answers:
                    self.memory.insert_interaction("assistant", answers, "socratic_answers", "hypothesis")

                for i, t in enumerate(thoughts, 1):
                    self.memory.insert_interaction("assistant", t, f"next_step_option_{i}", "hypothesis")

                # Re-enter refinement loop
                memory.set_var("stage", "refine")
                st.rerun()

