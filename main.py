#!/usr/bin/env python3
"""
Research Paper to Manim Animation Generator

A tool that converts academic research papers into beautiful 3Blue1Brown-style
mathematical animations with professional voiceovers.

Features:
- Gemini Deep Research for semantic analysis
- Claude Opus 4.5 for Manim code generation
- ElevenLabs for professional voiceovers
- Concurrent generation for faster processing
- Automatic video stitching

Usage:
    python main.py <path_to_pdf>
    python main.py <path_to_pdf> --fast       # Skip deep research
    python main.py <path_to_pdf> --no-voice   # Skip voiceover
    python main.py <path_to_pdf> --sequential # No concurrent generation
    python main.py --demo                     # Run with a test scene
"""

import sys
import os
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv()

console = Console()


def check_dependencies():
    """Check that all required dependencies are available."""
    errors = []
    warnings = []
    
    if not os.getenv("GOOGLE_API_KEY"):
        errors.append("GOOGLE_API_KEY not found in environment")
    if not os.getenv("ANTHROPIC_API_KEY"):
        errors.append("ANTHROPIC_API_KEY not found in environment")
    if not os.getenv("ELEVENLABS_API_KEY"):
        warnings.append("ELEVENLABS_API_KEY not found - voiceovers will be disabled")
    
    try:
        import manim
    except ImportError:
        errors.append("Manim not installed. Run: pip install manim")
    
    try:
        import subprocess
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        if result.returncode != 0:
            errors.append("FFmpeg not found. Please install FFmpeg.")
    except FileNotFoundError:
        errors.append("FFmpeg not found. Please install FFmpeg.")
    
    if errors:
        console.print("[red]Missing dependencies:[/red]")
        for error in errors:
            console.print(f"  • {error}")
        return False
    
    if warnings:
        console.print("[yellow]Warnings:[/yellow]")
        for warning in warnings:
            console.print(f"  • {warning}")
    
    return True


def run_demo():
    """Run a demo animation without a PDF."""
    from src.claude_mcp_animator import ClaudeMCPAnimator
    
    console.print(Panel.fit(
        "[bold blue]Demo Mode[/bold blue]\n"
        "Generating a sample animation...",
        border_style="blue"
    ))
    
    demo_scene = {
        "scene_number": 1,
        "title": "The Beauty of Euler's Identity",
        "visual_description": """
        Start with a complex plane (Axes). Draw the unit circle in blue.
        Show e^(i*theta) as a point moving around the circle as theta increases from 0 to pi.
        When theta reaches pi, highlight the point at (-1, 0) and show Euler's identity.
        Display the equation e^(i*pi) + 1 = 0 in the center with a golden glow effect.
        """,
        "latex_equations": [
            r"e^{i\theta} = \cos\theta + i\sin\theta",
            r"e^{i\pi} + 1 = 0"
        ],
        "narration": "Euler's identity connects five fundamental constants in one elegant equation.",
        "key_insight": "e raised to i*pi equals -1, revealing deep connections between exponentials and trigonometry.",
        "manim_hints": "Use ComplexPlane, ParametricFunction for the circle, MathTex for equations, Indicate for highlights"
    }
    
    animator = ClaudeMCPAnimator()
    code, video_path = animator.generate_animation(demo_scene, 0)
    
    if video_path:
        console.print(f"\n[green]✓ Demo video created:[/green] {video_path}")
        console.print("\n[dim]Open the video file to see the animation![/dim]")
    else:
        console.print("\n[yellow]Animation code generated but rendering failed.[/yellow]")
        console.print("[dim]Check that Manim and FFmpeg are properly installed.[/dim]")
    
    return video_path


def main():
    """Main entry point."""
    console.print(Panel.fit(
        "[bold cyan]Research Paper → Animation Generator[/bold cyan]\n"
        "[dim]Gemini Deep Research + Claude Opus 4.5 + Manim + ElevenLabs[/dim]",
        border_style="cyan"
    ))
    
    if not check_dependencies():
        console.print("\n[yellow]Please fix the above issues and try again.[/yellow]")
        sys.exit(1)
    
    if len(sys.argv) < 2:
        console.print("\n[bold]Usage:[/bold]")
        console.print("  python main.py <path_to_pdf>           Process a research paper")
        console.print("  python main.py <path_to_pdf> --fast    Skip deep research")
        console.print("  python main.py <path_to_pdf> --no-voice Skip voiceover generation")
        console.print("  python main.py <path_to_pdf> --sequential No concurrent generation")
        console.print("  python main.py --demo                  Run demo animation")
        console.print("\n[bold]Setup:[/bold]")
        console.print("  1. Copy .env.example to .env")
        console.print("  2. Add your API keys:")
        console.print("     - GOOGLE_API_KEY")
        console.print("     - ANTHROPIC_API_KEY")
        console.print("     - ELEVENLABS_API_KEY (optional)")
        console.print("  3. Install: pip install -r requirements.txt")
        sys.exit(0)
    
    if sys.argv[1] == "--demo":
        run_demo()
        return
    
    pdf_path = sys.argv[1]
    use_deep_research = "--fast" not in sys.argv
    include_voiceover = "--no-voice" not in sys.argv
    concurrent = "--sequential" not in sys.argv
    
    if not os.getenv("ELEVENLABS_API_KEY"):
        include_voiceover = False
        console.print("[yellow]No ElevenLabs API key found - skipping voiceovers[/yellow]")
    
    if not Path(pdf_path).exists():
        console.print(f"[red]File not found:[/red] {pdf_path}")
        sys.exit(1)
    
    if not pdf_path.lower().endswith(".pdf"):
        console.print("[yellow]Warning: File does not have .pdf extension[/yellow]")
    
    from src.pipeline import ResearchToAnimationPipeline
    
    pipeline = ResearchToAnimationPipeline()
    result = pipeline.process_paper(
        pdf_path,
        use_deep_research=use_deep_research,
        concurrent_generation=concurrent,
        include_voiceover=include_voiceover,
    )
    
    if result.get("success"):
        console.print(f"\n[bold green]Success![/bold green]")
        console.print(f"\n[bold]Final Video:[/bold] {result.get('final_video')}")
        console.print(f"\n[dim]Run 'start \"{result.get('final_video')}\"' to view[/dim]")
    else:
        console.print(f"\n[red]Pipeline failed: {result.get('error', 'Unknown error')}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
