from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseAgent(ABC):
    def __init__(self, name: str, desc: Optional[str] = None):
        self.name = name
        self.desc = desc

    @abstractmethod
    def confidence(self, params) -> float:
        """ Return confidence score to handle states """
        raise NotImplementedError

    @abstractmethod
    def run_agent(self, memory):
        """ Render UI + handles agent interactions"""
        raise NotImplementedError