from typing import Dict, Any, Optional

from app.agents.base import BaseAgent
from app.tools.memory import MemoryManager

try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except (ImportError, RuntimeError):
    STREAMLIT_AVAILABLE = False
    st = None


class FallbackAgent(BaseAgent):
    """
    Fallback agent that handles routing failures and provides error recovery.
    This agent is called when:
    - No other agent has sufficient confidence to handle a request
    - An agent fails during execution
    - Manual workflow is exhausted
    """
    
    def __init__(self, name: str = "Fallback Agent", desc: Optional[str] = None):
        super().__init__(name, desc or "Handles routing failures and provides error recovery")
        self.memory = MemoryManager()

    def confidence(self, payload: Dict[str, Any]) -> float:
        """
        Fallback agent has low confidence by default - it should only be used
        when no other agent can handle the request.
        """
        # Only confident if explicitly requested as fallback
        if payload.get("force_fallback") or payload.get("error_occurred"):
            return 1.0
        return 0.0

    def run_agent(self, memory: MemoryManager) -> Dict[str, Any]:
        """
        Handle fallback scenarios - provide user feedback and recovery options.
        """
        memory.log_event(
            event_type="fallback",
            payload={
                "message": "Fallback agent activated",
                "reason": "No suitable agent found or routing error occurred"
            },
            mode="fallback"
        )

        if STREAMLIT_AVAILABLE and st is not None:
            st.error("Routing Error: Unable to determine next agent")
            st.markdown("""
            The system was unable to route your request to an appropriate agent.
            This can happen when:
            - No agent has sufficient confidence to handle the current state
            - The manual workflow has been exhausted
            - An error occurred during agent execution
            """)
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Retry Routing", use_container_width=True):
                    memory.set_var("workflow_index", 0)
                    st.rerun()
            with col2:
                if st.button("Go to Home", use_container_width=True):
                    st.switch_page("pages/home.py")
            with col3:
                if st.button("Check Settings", use_container_width=True):
                    st.switch_page("pages/settings.py")
            with st.expander("Debug Information", expanded=False):
                st.json({
                    "routing_mode": memory.get_var("routing_mode", "Unknown"),
                    "workflow_index": memory.get_var("workflow_index", 0),
                    "manual_workflow": memory.get_var("manual_workflow", []),
                    "last_hypothesis": memory.get_var("last_hypothesis") is not None,
                    "experimental_outputs": memory.get_var("experimental_outputs") is not None,
                    "uploaded_files": len(memory.get_var("uploaded_files", [])),
                })
            st.info("Tip: Try adjusting your routing mode in Settings or ensure prerequisite steps are complete.")

        return {"status": "error", "message": "No suitable agent found or routing error occurred."}