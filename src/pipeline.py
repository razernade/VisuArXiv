"""
Research-to-Animation Pipeline

Orchestrates the full workflow:
1. Check Supabase cache for existing video
2. Upload PDF → Gemini Deep Research
3. Structured output → Claude Animator (concurrent)
4. Manim code → Rendered videos
5. Generate voiceovers (concurrent)
6. Combine audio + video with pauses between scenes
7. Stitch into final video
8. Upload to Supabase cache
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .gemini_researcher import GeminiResearcher
from .claude_mcp_animator import ClaudeMCPAnimator
from .voiceover import VoiceoverGenerator
from .video_composer import VideoComposer
from .supabase_cache import get_video_cache, SupabaseVideoCache

console = Console()


class ResearchToAnimationPipeline:
    """Full pipeline from research paper to animated visualization with voiceover."""

    def __init__(
        self,
        google_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        elevenlabs_api_key: Optional[str] = None,
    ):
        self.researcher = GeminiResearcher(api_key=google_api_key)
        self.animator = ClaudeMCPAnimator(api_key=anthropic_api_key)
        self.voiceover = VoiceoverGenerator(api_key=elevenlabs_api_key)
        self.composer = VideoComposer()
        self.cache = get_video_cache()
        
        self.output_dir = Path(__file__).parent.parent / "output"
        self.output_dir.mkdir(exist_ok=True)

    def _get_paper_identifier(self, pdf_path: str) -> str:
        """Extract a unique identifier from the PDF path."""
        # Use filename as identifier (could be arxiv ID or title)
        return Path(pdf_path).stem

    def process_paper(
        self,
        pdf_path: str,
        use_deep_research: bool = True,
        concurrent_generation: bool = True,
        max_workers: int = 3,
        scenes_to_generate: Optional[list[int]] = None,
        include_voiceover: bool = True,
        use_cache: bool = True,
        section_pause: float = 2.0,
    ) -> dict:
        """
        Process a research paper and generate a complete video with voiceover.
        
        Args:
            pdf_path: Path to the research paper PDF
            use_deep_research: Whether to use Gemini Deep Research (slower but thorough)
            concurrent_generation: Whether to generate animations concurrently
            max_workers: Number of concurrent workers
            scenes_to_generate: List of scene indices to generate (None = all)
            include_voiceover: Whether to generate voiceovers
            use_cache: Whether to check/use Supabase cache
            section_pause: Seconds of pause between each scene
            
        Returns:
            Summary dictionary with results
        """
        console.print(Panel.fit(
            "[bold blue]Research-to-Animation Pipeline[/bold blue]\n"
            f"Processing: {pdf_path}",
            border_style="blue"
        ))
        
        paper_identifier = self._get_paper_identifier(pdf_path)
        
        # Step 0: Check Supabase cache
        if use_cache:
            console.print("\n[bold]Checking Cache[/bold]")
            console.print("─" * 50)
            
            cached, cached_url, cached_metadata = self.cache.check_cache(paper_identifier)
            if cached and cached_url:
                console.print(f"[green]✓ Found cached video for this paper![/green]")
                console.print(f"[dim]URL: {cached_url}[/dim]")
                
                # Download to local for playback
                local_cached = self.cache.download_cached_video(paper_identifier, self.output_dir)
                
                return {
                    "success": True,
                    "cached": True,
                    "timestamp": datetime.now().isoformat(),
                    "paper_title": cached_metadata.get("paper_title", paper_identifier) if cached_metadata else paper_identifier,
                    "final_video": str(local_cached) if local_cached else cached_url,
                    "video_url": cached_url,
                    "output_directory": str(self.output_dir),
                }
        
        console.print("\n[bold]Step 1: Analyzing Research Paper[/bold]")
        console.print("─" * 50)
        
        research_data = self.researcher.analyze_paper(pdf_path, use_deep_research)
        
        research_output_path = self.output_dir / "research_output.json"
        research_output_path.write_text(json.dumps(research_data, indent=2), encoding="utf-8")
        console.print(f"[dim]Research data saved to: {research_output_path}[/dim]")
        
        if "error" in research_data or not research_data.get("scenes"):
            console.print("[red]Failed to extract scenes from paper[/red]")
            return {"success": False, "error": "Research extraction failed", "data": research_data}
        
        self._display_research_summary(research_data)
        
        scenes = research_data.get("scenes", [])
        if scenes_to_generate is not None:
            scenes = [s for i, s in enumerate(scenes) if i in scenes_to_generate]
        
        console.print("\n[bold]Step 2: Generating Animations[/bold]")
        console.print("─" * 50)
        
        if concurrent_generation:
            animation_results = self.animator.generate_animations_concurrent(scenes, max_workers)
        else:
            animation_results = []
            for i, scene in enumerate(scenes):
                code, video_path = self.animator.generate_animation(scene, i)
                animation_results.append((code, video_path))
        
        video_paths = [vp for _, vp in animation_results if vp is not None]
        
        if not video_paths:
            console.print("[red]No animations were successfully generated[/red]")
            return {"success": False, "error": "Animation generation failed"}
        
        if include_voiceover:
            console.print("\n[bold]Step 3: Generating Voiceovers[/bold]")
            console.print("─" * 50)
            
            successful_scenes = [scenes[i] for i, (_, vp) in enumerate(animation_results) if vp]
            audio_paths = self.voiceover.generate_all_voiceovers(
                successful_scenes,
                concurrent=concurrent_generation,
                max_workers=max_workers,
            )
            
            console.print("\n[bold]Step 4: Composing Final Video[/bold]")
            console.print("─" * 50)
            console.print(f"[dim]Adding {section_pause}s pause between scenes[/dim]")
            
            video_paths_list = [Path(vp) for vp in video_paths]
            
            final_video = self.composer.compose_full_video(
                video_paths_list,
                audio_paths,
                concurrent=concurrent_generation,
                max_workers=max_workers,
                section_pause=section_pause,
            )
        else:
            console.print("\n[bold]Step 3: Stitching Videos[/bold]")
            console.print("─" * 50)
            
            video_paths_list = [Path(vp) for vp in video_paths]
            final_video = self.composer.stitch_videos(video_paths_list)
        
        # Step 5: Upload to Supabase cache
        if use_cache and final_video and final_video.exists():
            console.print("\n[bold]Step 5: Caching Video[/bold]")
            console.print("─" * 50)
            
            cache_metadata = {
                "paper_title": research_data.get("paper_title", "Unknown"),
                "total_scenes": len(animation_results),
                "successful_renders": len(video_paths),
                "generation_timestamp": datetime.now().isoformat(),
            }
            
            success, video_url = self.cache.upload_video(
                final_video,
                paper_identifier,
                metadata=cache_metadata,
            )
            
            if success:
                console.print(f"[green]✓ Video cached for future queries[/green]")
        else:
            video_url = None
        
        summary = self._create_summary(research_data, animation_results, final_video, video_url)
        
        summary_path = self.output_dir / "pipeline_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        
        self._display_final_summary(summary)
        
        return summary

    def _display_research_summary(self, research_data: dict):
        """Display a summary of the research analysis."""
        console.print(f"\n[bold cyan]Paper:[/bold cyan] {research_data.get('paper_title', 'Unknown')}")
        console.print(f"[dim]{research_data.get('paper_summary', 'No summary available')}[/dim]")
        
        table = Table(title="\nExtracted Scenes", show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", width=40)
        table.add_column("Duration", width=10)
        table.add_column("Key Insight", width=50)
        
        for scene in research_data.get("scenes", []):
            table.add_row(
                str(scene.get("scene_number", "?")),
                scene.get("title", "Untitled")[:40],
                f"{scene.get('duration_seconds', '?')}s",
                scene.get("key_insight", "")[:50] + "..." if len(scene.get("key_insight", "")) > 50 else scene.get("key_insight", ""),
            )
        
        console.print(table)

    def _create_summary(self, research_data: dict, animation_results: list, final_video: Path, video_url: Optional[str] = None) -> dict:
        """Create a summary of the pipeline run."""
        successful = sum(1 for _, vp in animation_results if vp is not None)
        
        summary = {
            "success": True,
            "cached": False,
            "timestamp": datetime.now().isoformat(),
            "paper_title": research_data.get("paper_title", "Unknown"),
            "total_scenes": len(animation_results),
            "successful_renders": successful,
            "failed_renders": len(animation_results) - successful,
            "final_video": str(final_video),
            "output_directory": str(self.output_dir),
        }
        
        if video_url:
            summary["video_url"] = video_url
        
        return summary

    def _display_final_summary(self, summary: dict):
        """Display the final pipeline summary."""
        console.print("\n" + "═" * 60)
        console.print("[bold green]Pipeline Complete![/bold green]")
        console.print("═" * 60)
        
        if summary.get("cached"):
            console.print(f"\n[cyan]✓ Retrieved from cache[/cyan]")
        else:
            console.print(f"\n[green]✓ {summary['successful_renders']}/{summary['total_scenes']} scenes rendered[/green]")
        
        console.print(f"\n[bold]Final Video:[/bold] {summary['final_video']}")
        
        if summary.get("video_url"):
            console.print(f"[bold]Cached URL:[/bold] {summary['video_url']}")
        
        console.print(f"[dim]Output directory: {summary['output_directory']}[/dim]")


def run_pipeline(
    pdf_path: str,
    use_deep_research: bool = True,
    concurrent: bool = True,
    include_voiceover: bool = True,
    use_cache: bool = True,
    section_pause: float = 2.0,
) -> dict:
    """Convenience function to run the full pipeline."""
    from dotenv import load_dotenv
    load_dotenv()
    
    pipeline = ResearchToAnimationPipeline()
    return pipeline.process_paper(
        pdf_path,
        use_deep_research=use_deep_research,
        concurrent_generation=concurrent,
        include_voiceover=include_voiceover,
        use_cache=use_cache,
        section_pause=section_pause,
    )


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        console.print("[red]Usage: python -m src.pipeline <path_to_pdf> [options][/red]")
        console.print("\nOptions:")
        console.print("  --fast         Use standard analysis instead of deep research")
        console.print("  --sequential   Generate animations sequentially (slower)")
        console.print("  --no-voice     Skip voiceover generation")
        console.print("  --no-cache     Skip Supabase caching")
        console.print("  --pause=N      Set pause between scenes in seconds (default: 2.0)")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    use_deep_research = "--fast" not in sys.argv
    concurrent = "--sequential" not in sys.argv
    include_voice = "--no-voice" not in sys.argv
    use_cache = "--no-cache" not in sys.argv
    
    # Parse pause duration
    section_pause = 2.0
    for arg in sys.argv:
        if arg.startswith("--pause="):
            try:
                section_pause = float(arg.split("=")[1])
            except:
                pass
    
    result = run_pipeline(
        pdf_path,
        use_deep_research=use_deep_research,
        concurrent=concurrent,
        include_voiceover=include_voice,
        use_cache=use_cache,
        section_pause=section_pause,
    )
    
    if result.get("success"):
        sys.exit(0)
    else:
        sys.exit(1)
