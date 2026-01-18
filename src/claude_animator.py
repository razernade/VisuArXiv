"""
Claude Animator Module

Uses Claude Opus 4.5 to generate Manim code from structured research data.
Implements agentic self-correction for robust code generation.
"""

import os
import re
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple
import anthropic
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel

console = Console()


class ClaudeAnimator:
    """Generates and executes Manim animations using Claude."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = "claude-opus-4-5-20251101"
        
        self.system_prompt = self._load_system_prompt()
        self.output_dir = Path(__file__).parent.parent / "output"
        self.output_dir.mkdir(exist_ok=True)
        
        self.max_retries = 3

    def _load_system_prompt(self) -> str:
        prompt_path = Path(__file__).parent.parent / "system_prompt.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return "You are a Manim animation expert. Generate clean, runnable ManimCE code."

    def generate_animation(self, scene_data: dict, scene_index: int = 0) -> Tuple[str, Optional[Path]]:
        """
        Generate Manim code for a single scene.
        
        Args:
            scene_data: Scene specification from Gemini research output
            scene_index: Index for naming the output file
            
        Returns:
            Tuple of (generated_code, video_path or None if failed)
        """
        prompt = self._build_generation_prompt(scene_data)
        
        console.print(f"\n[blue]Generating animation for:[/blue] {scene_data.get('title', 'Untitled')}")
        
        code = None
        video_path = None
        last_error = None
        
        for attempt in range(self.max_retries):
            if attempt == 0:
                current_prompt = prompt
            else:
                current_prompt = self._build_correction_prompt(code, last_error)
                console.print(f"[yellow]Retry {attempt + 1}/{self.max_retries}: Correcting code...[/yellow]")
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                messages=[{"role": "user", "content": current_prompt}]
            )
            
            code = self._extract_code(response.content[0].text)
            
            if not code:
                console.print("[red]No code block found in response[/red]")
                continue
            
            success, result = self._render_animation(code, scene_index)
            
            if success:
                video_path = result
                console.print(f"[green]✓ Animation rendered successfully![/green]")
                break
            else:
                last_error = result
                console.print(f"[red]Render failed:[/red] {result[:200]}...")
        
        return code, video_path

    def generate_full_video(self, research_data: dict) -> list[Tuple[str, Optional[Path]]]:
        """
        Generate animations for all scenes in the research data.
        
        Args:
            research_data: Full output from Gemini researcher
            
        Returns:
            List of (code, video_path) tuples for each scene
        """
        scenes = research_data.get("scenes", [])
        if not scenes:
            console.print("[red]No scenes found in research data[/red]")
            return []
        
        console.print(f"\n[bold blue]Generating {len(scenes)} animations...[/bold blue]")
        
        results = []
        for i, scene in enumerate(scenes):
            code, video_path = self.generate_animation(scene, i)
            results.append((code, video_path))
        
        successful = sum(1 for _, path in results if path is not None)
        console.print(f"\n[bold]Completed: {successful}/{len(scenes)} animations rendered successfully[/bold]")
        
        return results

    def _build_generation_prompt(self, scene_data: dict) -> str:
        """Build the prompt for initial code generation."""
        return f"""Create a Manim animation for the following scene:

## Scene Title
{scene_data.get('title', 'Untitled Scene')}

## Visual Description
{scene_data.get('visual_description', 'No description provided')}

## Key Equations (LaTeX)
{json.dumps(scene_data.get('latex_equations', []), indent=2)}

## Narration/Explanation
{scene_data.get('narration', 'No narration')}

## Key Insight
{scene_data.get('key_insight', 'No insight provided')}

## Manim Hints
{scene_data.get('manim_hints', 'Use appropriate Manim objects')}

Generate a complete, self-contained Manim scene class that visualizes this concept.
Follow the 3Blue1Brown style guidelines strictly.
The scene class should be named Scene{scene_data.get('scene_number', 1):02d}.
"""

    def _build_correction_prompt(self, failed_code: str, error: str) -> str:
        """Build prompt for code correction after a failed render."""
        return f"""The following Manim code failed to render:

```python
{failed_code}
```

## Error Message
```
{error}
```

Please fix the code. Common issues to check:
1. Missing imports (use `from manim import *`)
2. Invalid LaTeX (use raw strings: r"\\frac{{x}}{{y}}")
3. Deprecated methods (use Create instead of ShowCreation)
4. Invalid parameters (Text() doesn't accept text_align)
5. Objects outside screen bounds

Return ONLY the corrected Python code.
"""

    def _extract_code(self, response: str) -> Optional[str]:
        """Extract Python code block from response."""
        pattern = r"```python\s*(.*?)```"
        matches = re.findall(pattern, response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        if "from manim import" in response or "class " in response:
            return response.strip()
        
        return None

    def _render_animation(self, code: str, scene_index: int) -> Tuple[bool, str]:
        """
        Render the Manim animation.
        
        Returns:
            Tuple of (success, result) where result is video path on success or error message on failure
        """
        scene_name = self._extract_scene_name(code)
        if not scene_name:
            return False, "Could not find scene class name in code"
        
        script_path = self.output_dir / f"scene_{scene_index:02d}.py"
        script_path.write_text(code, encoding="utf-8")
        
        console.print(f"[dim]Rendering {scene_name}...[/dim]")
        
        try:
            result = subprocess.run(
                [
                    "manim",
                    "-ql",
                    "--disable_caching",
                    "-o", f"scene_{scene_index:02d}",
                    str(script_path),
                    scene_name,
                ],
                cwd=str(self.output_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            if result.returncode == 0:
                video_pattern = self.output_dir / "media" / "videos" / f"scene_{scene_index:02d}" / "480p15" / f"scene_{scene_index:02d}.mp4"
                
                if video_pattern.exists():
                    return True, str(video_pattern)
                
                for mp4 in (self.output_dir / "media").rglob("*.mp4"):
                    return True, str(mp4)
                
                return True, "Video rendered but path unknown"
            else:
                error = result.stderr or result.stdout
                return False, error
                
        except subprocess.TimeoutExpired:
            return False, "Render timeout exceeded (120s)"
        except FileNotFoundError:
            return False, "Manim not found. Install with: pip install manim"
        except Exception as e:
            return False, str(e)

    def _extract_scene_name(self, code: str) -> Optional[str]:
        """Extract the scene class name from code."""
        pattern = r"class\s+(\w+)\s*\(\s*(?:Scene|ThreeDScene|MovingCameraScene)"
        match = re.search(pattern, code)
        return match.group(1) if match else None


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    animator = ClaudeAnimator()
    
    test_scene = {
        "scene_number": 1,
        "title": "Introduction to Derivatives",
        "visual_description": "Show a curve with a tangent line that slides along it, demonstrating the concept of instantaneous rate of change",
        "latex_equations": [r"\frac{df}{dx}", r"\lim_{h \to 0} \frac{f(x+h) - f(x)}{h}"],
        "narration": "The derivative represents the instantaneous rate of change at any point on a curve.",
        "key_insight": "The tangent line's slope equals the derivative at that point.",
        "manim_hints": "Use Axes, plot a smooth curve, animate a tangent line moving along it"
    }
    
    code, video_path = animator.generate_animation(test_scene, 0)
    
    if video_path:
        print(f"\nVideo saved to: {video_path}")
    else:
        print("\nFailed to render animation")
        print("Generated code:")
        print(code)
