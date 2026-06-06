"""A singly linked list with append, get, and reverse."""


class Node:
    def __init__(self, value, nxt=None):
        self.value = value
        self.next = nxt


class LinkedList:
    def __init__(self):
        self.head: Node | None = None
        self._size = 0

    def append(self, value) -> None:
        node = Node(value)
        if self.head is None:
            self.head = node
        else:
            cur = self.head
            while cur.next is not None:
                cur = cur.next
            cur.next = node
        self._size += 1

    def get(self, index: int):
        if index < 0 or index >= self._size:
            raise IndexError("index out of range")
        cur = self.head
        for _ in range(index):
            cur = cur.next
        return cur.value

    def reverse(self) -> None:
        prev = None
        cur = self.head
        while cur is not None:
            nxt = cur.next
            cur.next = prev
            prev = cur
            cur = nxt
        self.head = prev

    def to_list(self) -> list:
        out = []
        cur = self.head
        while cur is not None:
            out.append(cur.value)
            cur = cur.next
        return out

    def __len__(self) -> int:
        return self._size
