"""RTL Intel: lightweight lint and design intelligence for RTL."""

from .analyzer import analyze_paths
from .models import AnalysisReport, Issue, Module
from .parser import VerilogParser

__all__ = ["AnalysisReport", "Issue", "Module", "VerilogParser", "analyze_paths"]
__version__ = "0.1.0"

