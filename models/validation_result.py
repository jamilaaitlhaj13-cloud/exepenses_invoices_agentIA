from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """
    Represents the result returned by ValidationTool
    after checking an invoice's business rules.
    """
    is_valid: bool
    errors:   list = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """
        Adds an error message and marks the result as invalid.
        Using this method ensures is_valid is always set to False
        when an error is added.
        """
        self.errors.append(message)
        self.is_valid = False

    def __bool__(self) -> bool:
        """
        Allows using the result directly in an if statement.
        Example: if result: ...
        """
        return self.is_valid