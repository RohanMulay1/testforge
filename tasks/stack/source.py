"""A bounded LIFO stack with explicit error behavior."""


class StackError(Exception):
    pass


class Stack:
    def __init__(self, capacity: int = 0):
        if capacity < 0:
            raise ValueError("capacity must be >= 0")
        self._capacity = capacity
        self._items: list = []

    def push(self, item) -> None:
        if self._capacity and len(self._items) >= self._capacity:
            raise StackError("stack is full")
        self._items.append(item)

    def pop(self):
        if not self._items:
            raise StackError("pop from empty stack")
        return self._items.pop()

    def peek(self):
        if not self._items:
            raise StackError("peek from empty stack")
        return self._items[-1]

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def __len__(self) -> int:
        return len(self._items)
