from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
import logging
from threading import Lock


@dataclass
class Message:
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if not self.content.strip():
            raise ValueError("Message content cannot be empty")
        if self.role not in ["user", "assistant"]:
            raise ValueError("Invalid role. Must be 'user' or 'assistant'")


@dataclass
class ChatHistory:
    messages: List[Message] = field(default_factory=list)
    max_messages: int = 100

    def add_message(self, role: str, content: str) -> None:
        """Add a message with validation and message limit enforcement"""
        if len(self.messages) >= self.max_messages:
            self.messages.pop(0)  # Remove oldest message
        self.messages.append(Message(role=role, content=content))

    def add_user_message(self, message: str) -> None:
        self.add_message("user", message)

    def add_assistant_message(self, message: str) -> None:
        self.add_message("assistant", message)

    def get_messages(self) -> List[Dict]:
        return [{"role": msg.role, "content": msg.content} for msg in self.messages]

    def get_messages_as_string(self) -> str:
        return "\n".join(
            f"{msg.role.capitalize()}: {msg.content}" for msg in self.messages
        )


class ChatHistoryManager:
    def __init__(self, max_threads: int = 1000, thread_timeout_hours: int = 24):
        self.chat_histories: Dict[str, ChatHistory] = {}
        self.max_threads = max_threads
        self.thread_timeout_hours = thread_timeout_hours
        self.lock = Lock()
        self.last_access: Dict[str, datetime] = {}

    def _cleanup_old_threads(self) -> None:
        """Remove threads that haven't been accessed in thread_timeout_hours"""
        current_time = datetime.now()
        with self.lock:
            threads_to_remove = [
                thread_id for thread_id, last_access in self.last_access.items()
                if (current_time - last_access).total_seconds() > self.thread_timeout_hours * 3600
            ]
            for thread_id in threads_to_remove:
                del self.chat_histories[thread_id]
                del self.last_access[thread_id]

    def get_chat_history(self, thread_id: str) -> ChatHistory:
        with self.lock:
            if len(self.chat_histories) >= self.max_threads:
                self._cleanup_old_threads()
                if len(self.chat_histories) >= self.max_threads:
                    raise RuntimeError("Maximum number of active threads reached")

            if thread_id not in self.chat_histories:
                self.chat_histories[thread_id] = ChatHistory()

            self.last_access[thread_id] = datetime.now()
            return self.chat_histories[thread_id]

    def add_user_message(self, thread_id: str, message: str) -> None:
        chat_history = self.get_chat_history(thread_id)
        chat_history.add_user_message(message)

    def add_assistant_message(self, thread_id: str, message: str) -> None:
        chat_history = self.get_chat_history(thread_id)
        chat_history.add_assistant_message(message)

    def get_thread_messages_as_string(self, thread_id: str) -> str:
        with self.lock:
            if thread_id not in self.chat_histories:
                return ""
            self.last_access[thread_id] = datetime.now()
            return self.chat_histories[thread_id].get_messages_as_string()

    def remove_thread(self, thread_id: str) -> None:
        """Manually remove a thread from history"""
        with self.lock:
            self.chat_histories.pop(thread_id, None)
            self.last_access.pop(thread_id, None)


# Single instance for application-wide use
chat_history_manager = ChatHistoryManager()
