class HclParseError(ValueError):
    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(f"line {line}: {message}" if line else message)
        self.line = line
