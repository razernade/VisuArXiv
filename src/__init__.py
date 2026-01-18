"""
Research-to-Animation Pipeline Source Package

Modules:
- arxiv_loader: Search and download arXiv papers
- gemini_researcher: Analyze papers using Gemini
- claude_mcp_animator: Generate Manim animations using Claude
- voiceover: Generate voiceovers with ElevenLabs
- video_composer: Combine videos with audio and stitch scenes
- supabase_cache: Cache generated videos in Supabase
- pipeline: Orchestrate the full workflow
"""

from .arxiv_loader import search_arxiv, download_arxiv_pdf
from .supabase_cache import get_video_cache, SupabaseVideoCache
from .pipeline import ResearchToAnimationPipeline, run_pipeline

__all__ = [
    "search_arxiv",
    "download_arxiv_pdf",
    "get_video_cache",
    "SupabaseVideoCache",
    "ResearchToAnimationPipeline",
    "run_pipeline",
]
