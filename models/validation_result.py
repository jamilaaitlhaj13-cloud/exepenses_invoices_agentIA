# models/validation_result.py

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """
    Represents the result returned by ValidationTool
    after checking an invoice's business rules.
    
    Attributes:
        is_valid : True if all blocking rules passed
        errors   : List of blocking error messages
        warnings : List of non-blocking warning messages
    """
    is_valid: bool = True
    errors:   list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """
        Adds an error message and marks the result as invalid.
        Using this method ensures is_valid is always set to False
        when an error is added.
        """
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """
        Adds a warning message without invalidating the result.
        Warnings are non-blocking and used for recommendations.
        """
        self.warnings.append(message)

    def __bool__(self) -> bool:
        """
        Allows using the result directly in an if statement.
        Example: if result: ...
        """
        return self.is_valid

    def has_errors(self) -> bool:
        """Returns True if there are any blocking errors."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Returns True if there are any warnings."""
        return len(self.warnings) > 0

    def summary(self) -> str:
        """
        Returns a human-readable summary of the validation result.
        """
        if self.is_valid and not self.warnings:
            return "✅ Validation passed — no issues"
        elif self.is_valid:
            return f"✅ Validation passed — {len(self.warnings)} warning(s)"
        else:
            return f"❌ Validation failed — {len(self.errors)} error(s), {len(self.warnings)} warning(s)"