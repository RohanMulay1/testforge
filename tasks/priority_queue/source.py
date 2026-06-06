"""A binary-heap-backed min priority queue."""

import heapq
import itertools


class PriorityQueue:
    def __init__(self):
        self._heap: list = []
        self._counter = itertools.count()

    def push(self, item, priority: float) -> None:
        # Tie-break on insertion order so equal priorities are FIFO and items
        # never need to be compared directly.
        entry = (priority, next(self._counter), item)
        heapq.heappush(self._heap, entry)

    def pop(self):
        if not self._heap:
            raise IndexError("pop from empty priority queue")
        priority, _count, item = heapq.heappop(self._heap)
        return item

    def peek(self):
        if not self._heap:
            raise IndexError("peek from empty priority queue")
        return self._heap[0][2]

    def __len__(self) -> int:
        return len(self._heap)

    def is_empty(self) -> bool:
        return not self._heap
