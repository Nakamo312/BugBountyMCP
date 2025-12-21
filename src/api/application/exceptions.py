"""Application specific exceptions"""

class AppError(Exception):
    """Base class for all application errors"""
    pass

class ToolNotFoundError(AppError):
    """Raised when the external tool binary is not found"""
    def __init__(self, tool_name: str, path: str):
        self.tool_name = tool_name
        self.path = path
        super().__init__(f"Tool binary not found: {tool_name} at {path}")

class ScanExecutionError(AppError):
    """Raised when a scan process fails (non-zero exit code or crash)"""
    pass