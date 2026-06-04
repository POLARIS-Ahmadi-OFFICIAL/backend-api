from functools import lru_cache

from app.tools.memory import MemoryManager


@lru_cache
def get_memory_manager() -> MemoryManager:
    memory = MemoryManager()
    memory.init_session()
    return memory
