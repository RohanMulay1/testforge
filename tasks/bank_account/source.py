"""A simple bank account with overdraft protection and transaction history."""


class InsufficientFunds(Exception):
    pass


class BankAccount:
    def __init__(self, balance: float = 0.0, overdraft_limit: float = 0.0):
        if balance < 0:
            raise ValueError("initial balance cannot be negative")
        if overdraft_limit < 0:
            raise ValueError("overdraft_limit cannot be negative")
        self._balance = float(balance)
        self._overdraft_limit = float(overdraft_limit)
        self.history: list[tuple[str, float]] = []

    @property
    def balance(self) -> float:
        return self._balance

    def deposit(self, amount: float) -> float:
        if amount <= 0:
            raise ValueError("deposit must be positive")
        self._balance += amount
        self.history.append(("deposit", amount))
        return self._balance

    def withdraw(self, amount: float) -> float:
        if amount <= 0:
            raise ValueError("withdrawal must be positive")
        if self._balance - amount < -self._overdraft_limit:
            raise InsufficientFunds("withdrawal exceeds overdraft limit")
        self._balance -= amount
        self.history.append(("withdraw", amount))
        return self._balance

    def transaction_count(self) -> int:
        return len(self.history)
