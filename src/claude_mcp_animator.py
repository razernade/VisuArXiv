"""
Claude MCP Animator Module

Uses Claude Opus 4.5 with MCP tools to generate Manim code.
- Uses GitMCP for live Manim documentation
- Uses local Manim MCP server for rendering

This version uses Claude's native tool calling to interact with MCP servers.
"""

import os
import re
import json
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import anthropic
from rich.console import Console
from rich.panel import Panel

console = Console()


RENDER_MANIM_TOOL = {
    "name": "render_manim",
    "description": """Render a Manim animation from Python code.
    
The code should contain a Scene class that inherits from manim.Scene.
Returns the path to the rendered video or error message.

IMPORTANT: Before writing code, consult the Manim documentation using fetch_manim_docs.

Quality options:
- 'low' (480p15) - fast preview
- 'medium' (720p30) - balanced  
- 'high' (1080p60) - production
""",
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Complete Python code containing a Manim Scene class"
            },
            "scene_name": {
                "type": "string",
                "description": "Name of the Scene class to render"
            },
            "quality": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Render quality (default: low)"
            }
        },
        "required": ["code", "scene_name"]
    }
}

VALIDATE_MANIM_TOOL = {
    "name": "validate_manim",
    "description": "Validate Manim code for syntax errors and common issues without rendering",
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to validate"
            }
        },
        "required": ["code"]
    }
}

FETCH_DOCS_TOOL = {
    "name": "fetch_manim_docs",
    "description": """Fetch documentation for a specific Manim class or function.
    
Use this BEFORE writing code to ensure you're using the correct API.
Examples: 'Axes', 'NumberLine', 'MathTex', 'Create', 'Transform'
""",
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The Manim class or function to look up (e.g., 'Axes', 'MathTex')"
            }
        },
        "required": ["topic"]
    }
}

TOOLS = [RENDER_MANIM_TOOL, VALIDATE_MANIM_TOOL, FETCH_DOCS_TOOL]


class ClaudeMCPAnimator:
    """Generates and executes Manim animations using Claude with MCP tools."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = "claude-opus-4-5-20251101"
        
        self.system_prompt = self._load_system_prompt()
        self.output_dir = Path(__file__).parent.parent / "output"
        self.output_dir.mkdir(exist_ok=True)
        
        self.max_iterations = 5

    def _load_system_prompt(self) -> str:
        prompt_path = Path(__file__).parent.parent / "system_prompt.txt"
        base_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        
        mcp_instructions = """

## MCP TOOL USAGE INSTRUCTIONS

You have access to the following tools:

1. **fetch_manim_docs**: ALWAYS use this first to look up the correct API for any Manim class you want to use.
   - Check documentation before using: Axes, NumberLine, MathTex, Text, etc.
   - This ensures you use the correct parameters and avoid deprecated methods.

2. **validate_manim**: Use this to check your code for issues before rendering.
   - Catches syntax errors, missing imports, deprecated methods.
   
3. **render_manim**: Render your animation to video.
   - Start with quality='low' for fast previews.
   - If rendering fails, analyze the error, fix the code, and try again.

## WORKFLOW

1. First, call fetch_manim_docs for each major class you plan to use
2. Write your Manim code based on the documentation
3. Call validate_manim to check for issues
4. Call render_manim to create the video
5. If there are errors, fix them and repeat steps 3-4

Always use the tools - never guess at the API!
"""
        return base_prompt + mcp_instructions

    def generate_animation(self, scene_data: dict, scene_index: int = 0) -> Tuple[str, Optional[Path]]:
        """
        Generate Manim code for a single scene using MCP tools.
        
        Args:
            scene_data: Scene specification from Gemini research output
            scene_index: Index for naming the output file
            
        Returns:
            Tuple of (generated_code, video_path or None if failed)
        """
        prompt = self._build_generation_prompt(scene_data)
        
        console.print(f"\n[blue]Generating animation for:[/blue] {scene_data.get('title', 'Untitled')}")
        
        messages = [{"role": "user", "content": prompt}]
        final_code = None
        video_path = None
        
        for iteration in range(self.max_iterations):
            console.print(f"[dim]Iteration {iteration + 1}/{self.max_iterations}[/dim]")
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=self.system_prompt,
                tools=TOOLS,
                messages=messages
            )
            
            if response.stop_reason == "tool_use":
                tool_results = []
                
                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_id = block.id
                        
                        console.print(f"[cyan]Tool call:[/cyan] {tool_name}")
                        
                        result = self._execute_tool(tool_name, tool_input, scene_index)
                        
                        if tool_name == "render_manim" and "✓" in result:
                            final_code = tool_input.get("code")
                            match = re.search(r"Video path: (.+\.mp4)", result)
                            if match:
                                video_path = Path(match.group(1))
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": result
                        })
                
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                
                if video_path:
                    console.print(f"[green]✓ Animation rendered successfully![/green]")
                    break
            else:
                for block in response.content:
                    if hasattr(block, "text"):
                        code_match = re.search(r"```python\s*(.*?)```", block.text, re.DOTALL)
                        if code_match:
                            final_code = code_match.group(1).strip()
                break
        
        return final_code, video_path

    def _build_generation_prompt(self, scene_data: dict) -> str:
        """Build the prompt for code generation."""
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

**Instructions:**
1. First, use fetch_manim_docs to look up the correct API for any Manim classes you plan to use
2. Write the animation code following 3Blue1Brown style
3. Validate the code with validate_manim
4. Render with render_manim (quality='low' for preview)

The scene class should be named Scene{scene_data.get('scene_number', 1):02d}.
"""

    def _execute_tool(self, tool_name: str, tool_input: dict, scene_index: int) -> str:
        """Execute a tool and return the result."""
        if tool_name == "render_manim":
            return self._render_manim(
                tool_input["code"],
                tool_input.get("scene_name", f"Scene{scene_index:02d}"),
                tool_input.get("quality", "low"),
                scene_index
            )
        elif tool_name == "validate_manim":
            return self._validate_manim(tool_input["code"])
        elif tool_name == "fetch_manim_docs":
            return self._fetch_manim_docs(tool_input["topic"])
        else:
            return f"Unknown tool: {tool_name}"

    def _render_manim(self, code: str, scene_name: str, quality: str, scene_index: int) -> str:
        """Render a Manim animation."""
        script_path = self.output_dir / f"scene_{scene_index:02d}.py"
        script_path.write_text(code, encoding="utf-8")
        
        quality_flags = {"low": "-ql", "medium": "-qm", "high": "-qh"}
        
        try:
            result = subprocess.run(
                [
                    "manim",
                    quality_flags.get(quality, "-ql"),
                    "--disable_caching",
                    str(script_path),
                    scene_name
                ],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(self.output_dir)
            )
            
            if result.returncode == 0:
                for mp4 in sorted(self.output_dir.rglob("*.mp4"), 
                                  key=lambda p: p.stat().st_mtime, reverse=True):
                    return f"✓ Animation rendered successfully!\n\nVideo path: {mp4}"
                return "✓ Render completed but video file not found."
            else:
                error = result.stderr or result.stdout
                return f"✗ Render failed!\n\nError:\n{error[:2000]}"
                
        except subprocess.TimeoutExpired:
            return "✗ Render timeout (180s exceeded)"
        except FileNotFoundError:
            return "✗ Manim not found. Install with: pip install manim"
        except Exception as e:
            return f"✗ Error: {str(e)}"

    def _validate_manim(self, code: str) -> str:
        """Validate Manim code."""
        issues = []
        
        try:
            compile(code, "<manim>", "exec")
        except SyntaxError as e:
            return f"✗ Syntax error at line {e.lineno}: {e.msg}"
        
        if "from manim import" not in code:
            issues.append("Missing: 'from manim import *'")
        
        if not re.search(r"class\s+\w+\s*\(\s*Scene", code):
            issues.append("No Scene class found")
        
        if "def construct(self)" not in code:
            issues.append("Missing construct method")
        
        deprecated = [("ShowCreation", "Create"), ("ApplyMethod", ".animate")]
        for old, new in deprecated:
            if old in code:
                issues.append(f"Deprecated: {old} → {new}")
        
        if issues:
            return "⚠ Issues found:\n" + "\n".join(f"• {i}" for i in issues)
        return "✓ Validation passed"

    def _fetch_manim_docs(self, topic: str) -> str:
        """Fetch Manim documentation for a topic."""
        docs = {
            "Axes": """
Axes(x_range=None, y_range=None, x_length=None, y_length=None, axis_config=None)

Parameters:
- x_range: [min, max, step] for x-axis
- y_range: [min, max, step] for y-axis  
- x_length: Length of x-axis in scene units
- y_length: Length of y-axis in scene units
- axis_config: Dict with 'color', 'include_tip', etc.

Methods:
- axes.plot(function, color=BLUE) - Plot a function
- axes.get_graph_label(graph, label) - Add label to graph
- axes.coords_to_point(x, y) - Convert coords to scene point
""",
            "NumberLine": """
NumberLine(x_range=None, length=None, include_numbers=False, ...)

Parameters:
- x_range: [min, max, step]
- length: Length in scene units
- include_numbers: Whether to show tick labels
- include_tip: Whether to show arrow tip

⚠️ DO NOT pass decimal_places to constructor!
Instead use: number_line.add_numbers(num_decimal_places=2)
""",
            "MathTex": """
MathTex(*tex_strings, font_size=48, color=WHITE)

⚠️ ALWAYS use raw strings: MathTex(r"\\frac{x}{y}")
⚠️ DO NOT use \\begin{align} - use VGroup of MathTex instead

Examples:
- MathTex(r"x^2 + y^2 = r^2")
- MathTex(r"\\int_0^1 x^2 dx")
- MathTex(r"\\frac{d}{dx}f(x)")
""",
            "Text": """
Text(text, font_size=48, color=WHITE, font=None)

⚠️ DO NOT use text_align or alignment parameters!
Position after creation with: .move_to(), .next_to(), .to_edge()

Examples:
- Text("Hello").to_edge(UP)
- Text("Subtitle", font_size=24).next_to(title, DOWN)
""",
            "Create": """
Create(mobject, lag_ratio=0.0, run_time=1.0)

Replacement for deprecated ShowCreation.
Draws the mobject from start to finish.

Example: self.play(Create(circle))
""",
            "Transform": """
Transform(mobject, target_mobject, run_time=1.0)

Morphs one mobject into another.

Example: self.play(Transform(square, circle))

Related:
- ReplacementTransform: Replaces rather than morphs
- TransformFromCopy: Creates copy then transforms
""",
            "animate": """
The .animate property for property interpolation.

⚠️ Use this instead of deprecated ApplyMethod!

Examples:
- circle.animate.shift(UP)
- square.animate.scale(2).rotate(PI/4)
- text.animate.set_color(YELLOW)

Usage: self.play(mobject.animate.method())
"""
        }
        
        topic_lower = topic.lower()
        for key, doc in docs.items():
            if key.lower() == topic_lower:
                return f"Documentation for {key}:\n{doc}"
        
        return f"""Documentation for '{topic}' not in local cache.

Common Manim classes:
- Axes, NumberLine, NumberPlane
- Circle, Square, Triangle, Polygon
- Arrow, Line, Vector
- MathTex, Tex, Text
- Create, Transform, FadeIn, FadeOut

Use these patterns:
- self.play(Create(obj)) - Animate creation
- self.play(obj.animate.shift(UP)) - Animate property change
- self.wait(1) - Pause for 1 second
"""

    def generate_full_video(self, research_data: dict) -> list[Tuple[str, Optional[Path]]]:
        """Generate animations for all scenes sequentially."""
        scenes = research_data.get("scenes", [])
        results = []
        
        for i, scene in enumerate(scenes):
            code, video_path = self.generate_animation(scene, i)
            results.append((code, video_path))
        
        return results

    def generate_animations_concurrent(
        self,
        scenes: list[dict],
        max_workers: int = 3,
    ) -> list[Tuple[str, Optional[Path]]]:
        """
        Generate animations for all scenes concurrently.
        
        Args:
            scenes: List of scene dictionaries
            max_workers: Number of concurrent generation tasks
            
        Returns:
            List of (code, video_path) tuples in order
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
        
        console.print(f"\n[bold blue]Generating {len(scenes)} animations concurrently...[/bold blue]")
        
        results = [None] * len(scenes)
        
        def generate_single(index: int, scene: dict) -> tuple[int, str, Optional[Path]]:
            code, video_path = self.generate_animation(scene, index)
            return index, code, video_path
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Generating animations...", total=len(scenes))
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(generate_single, i, scene): i
                    for i, scene in enumerate(scenes)
                }
                
                for future in as_completed(futures):
                    index, code, video_path = future.result()
                    results[index] = (code, video_path)
                    progress.advance(task)
        
        successful = sum(1 for _, vp in results if vp is not None)
        console.print(f"[green]✓ Generated {successful}/{len(scenes)} animations[/green]")
        
        return results


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    animator = ClaudeMCPAnimator()
    
    test_scene = {
        "scene_number": 1,
        "title": "Quadratic Function",
        "visual_description": "Show a parabola y=x^2 on coordinate axes with the vertex highlighted",
        "latex_equations": [r"y = x^2"],
        "narration": "The parabola opens upward with vertex at origin",
        "key_insight": "The vertex is the minimum point",
        "manim_hints": "Use Axes, plot the function, highlight vertex"
    }
    
    code, video = animator.generate_animation(test_scene, 0)
    print(f"Video: {video}")
