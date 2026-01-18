"""
Manim MCP Server

A Model Context Protocol server that provides tools for:
1. Rendering Manim animations
2. Validating Manim code
3. Managing output files

This server allows Claude to execute Manim code and get feedback.
"""

import os
import sys
import json
import subprocess
import tempfile
import re
from pathlib import Path
from datetime import datetime

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    print("MCP package not installed. Install with: pip install mcp", file=sys.stderr)


OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

if HAS_MCP:
    server = Server("manim-renderer")

    @server.list_tools()
    async def list_tools():
        """List available Manim tools."""
        return [
            Tool(
                name="render_manim",
                description="""Render a Manim animation from Python code.
                
                The code should contain a Scene class that inherits from manim.Scene.
                Returns the path to the rendered video or error message.
                
                Quality options:
                - 'low' (480p15) - fast preview
                - 'medium' (720p30) - balanced
                - 'high' (1080p60) - production
                """,
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Complete Python code containing a Manim Scene class"
                        },
                        "scene_name": {
                            "type": "string",
                            "description": "Name of the Scene class to render (optional, auto-detected if not provided)"
                        },
                        "quality": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "default": "low",
                            "description": "Render quality"
                        }
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="validate_manim",
                description="Validate Manim code for syntax errors without rendering",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to validate"
                        }
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="list_rendered_videos",
                description="List all rendered video files in the output directory",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="get_manim_example",
                description="Get an example of a working Manim scene",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["basic", "graph", "3d", "text", "transform"],
                            "description": "Type of example to return"
                        }
                    },
                    "required": ["type"]
                }
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Handle tool calls."""
        if name == "render_manim":
            return await render_manim(
                arguments["code"],
                arguments.get("scene_name"),
                arguments.get("quality", "low")
            )
        elif name == "validate_manim":
            return await validate_manim(arguments["code"])
        elif name == "list_rendered_videos":
            return await list_rendered_videos()
        elif name == "get_manim_example":
            return await get_manim_example(arguments["type"])
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def render_manim(code: str, scene_name: str = None, quality: str = "low"):
    """Render a Manim animation."""
    if not scene_name:
        match = re.search(r"class\s+(\w+)\s*\(\s*(?:Scene|ThreeDScene|MovingCameraScene)", code)
        if match:
            scene_name = match.group(1)
        else:
            return [TextContent(
                type="text",
                text="Error: Could not find a Scene class in the code. Make sure your class inherits from Scene."
            )]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_path = OUTPUT_DIR / f"scene_{timestamp}.py"
    script_path.write_text(code, encoding="utf-8")
    
    quality_flags = {
        "low": "-ql",
        "medium": "-qm",
        "high": "-qh"
    }
    
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "manim",
                quality_flags.get(quality, "-ql"),
                "--disable_caching",
                str(script_path),
                scene_name
            ],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(OUTPUT_DIR)
        )
        
        if result.returncode == 0:
            for mp4 in OUTPUT_DIR.rglob("*.mp4"):
                if timestamp in str(mp4) or scene_name in str(mp4):
                    return [TextContent(
                        type="text",
                        text=f"✓ Animation rendered successfully!\n\nVideo path: {mp4}\n\nYou can open this file to view the animation."
                    )]
            
            for mp4 in sorted(OUTPUT_DIR.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
                return [TextContent(
                    type="text",
                    text=f"✓ Animation rendered successfully!\n\nVideo path: {mp4}"
                )]
            
            return [TextContent(
                type="text",
                text=f"✓ Render completed but video file not found.\n\nStdout: {result.stdout}\n\nCheck the output directory: {OUTPUT_DIR}"
            )]
        else:
            error_msg = result.stderr or result.stdout
            return [TextContent(
                type="text",
                text=f"✗ Render failed!\n\nError:\n{error_msg}\n\nPlease fix the code and try again."
            )]
            
    except subprocess.TimeoutExpired:
        return [TextContent(
            type="text",
            text="✗ Render timeout (180s exceeded). The animation may be too complex."
        )]
    except FileNotFoundError:
        return [TextContent(
            type="text",
            text="✗ Manim not found. Please install with: pip install manim"
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"✗ Unexpected error: {str(e)}"
        )]


async def validate_manim(code: str):
    """Validate Manim code without rendering."""
    try:
        compile(code, "<manim_code>", "exec")
    except SyntaxError as e:
        return [TextContent(
            type="text",
            text=f"✗ Syntax error at line {e.lineno}:\n{e.msg}\n\n{e.text}"
        )]
    
    issues = []
    
    if "from manim import" not in code and "import manim" not in code:
        issues.append("Missing import: Add 'from manim import *' at the top")
    
    if not re.search(r"class\s+\w+\s*\(\s*(?:Scene|ThreeDScene|MovingCameraScene)", code):
        issues.append("No Scene class found. Create a class that inherits from Scene")
    
    if "def construct(self)" not in code:
        issues.append("Missing construct method. Add 'def construct(self):' to your Scene class")
    
    deprecated = [
        ("ShowCreation", "Create"),
        ("ShowPassingFlash", "Indicate"),
        ("ApplyMethod", ".animate syntax"),
    ]
    for old, new in deprecated:
        if old in code:
            issues.append(f"Deprecated: Replace '{old}' with '{new}'")
    
    if 'MathTex(' in code or 'Tex(' in code:
        tex_strings = re.findall(r'(?:MathTex|Tex)\s*\(\s*(["\'][^"\']+["\'])', code)
        for tex in tex_strings:
            if tex.startswith('"') and '\\' in tex and not tex.startswith('r"'):
                issues.append(f"LaTeX warning: Use raw string r{tex} to avoid escape issues")
    
    if issues:
        return [TextContent(
            type="text",
            text="⚠ Validation issues found:\n\n" + "\n".join(f"• {issue}" for issue in issues)
        )]
    
    return [TextContent(
        type="text",
        text="✓ Code validation passed! No obvious issues found."
    )]


async def list_rendered_videos():
    """List all rendered videos."""
    videos = list(OUTPUT_DIR.rglob("*.mp4"))
    
    if not videos:
        return [TextContent(
            type="text",
            text=f"No videos found in {OUTPUT_DIR}"
        )]
    
    videos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    
    lines = ["Rendered videos (newest first):\n"]
    for v in videos[:20]:
        size_mb = v.stat().st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(v.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        lines.append(f"• {v.name} ({size_mb:.1f} MB) - {mtime}")
        lines.append(f"  Path: {v}")
    
    return [TextContent(type="text", text="\n".join(lines))]


async def get_manim_example(example_type: str):
    """Return example Manim code."""
    examples = {
        "basic": '''from manim import *

class BasicExample(Scene):
    def construct(self):
        circle = Circle(color=BLUE_D, fill_opacity=0.5)
        square = Square(color=RED_D, fill_opacity=0.5)
        
        self.play(Create(circle))
        self.wait(1)
        
        self.play(Transform(circle, square))
        self.wait(1)
        
        self.play(FadeOut(circle))
''',
        "graph": '''from manim import *

class GraphExample(Scene):
    def construct(self):
        axes = Axes(
            x_range=[-3, 3, 1],
            y_range=[-2, 2, 1],
            axis_config={"color": GREY_B}
        )
        
        graph = axes.plot(lambda x: np.sin(x), color=BLUE_D)
        label = MathTex(r"f(x) = \\sin(x)", font_size=36).to_corner(UR)
        
        self.play(Create(axes))
        self.play(Create(graph), Write(label))
        self.wait(2)
''',
        "3d": '''from manim import *

class ThreeDExample(ThreeDScene):
    def construct(self):
        axes = ThreeDAxes()
        sphere = Sphere(radius=1, color=BLUE_D)
        
        self.set_camera_orientation(phi=75 * DEGREES, theta=30 * DEGREES)
        
        self.play(Create(axes))
        self.play(Create(sphere))
        self.begin_ambient_camera_rotation(rate=0.2)
        self.wait(3)
''',
        "text": '''from manim import *

class TextExample(Scene):
    def construct(self):
        title = Text("Hello, Manim!", font_size=48).to_edge(UP)
        
        equation = MathTex(r"E = mc^2", font_size=72)
        
        explanation = Text(
            "Energy equals mass times\\nthe speed of light squared",
            font_size=24
        ).next_to(equation, DOWN, buff=0.5)
        
        self.play(Write(title))
        self.wait(0.5)
        self.play(Write(equation))
        self.play(FadeIn(explanation))
        self.wait(2)
''',
        "transform": '''from manim import *

class TransformExample(Scene):
    def construct(self):
        shapes = VGroup(
            Circle(color=RED_D),
            Square(color=GREEN),
            Triangle(color=BLUE_D)
        ).arrange(RIGHT, buff=1)
        
        self.play(Create(shapes))
        self.wait(1)
        
        # Animate properties
        self.play(
            shapes[0].animate.scale(1.5),
            shapes[1].animate.rotate(PI/4),
            shapes[2].animate.set_fill(YELLOW, opacity=0.8)
        )
        self.wait(1)
        
        # Transform all to circles
        circles = VGroup(*[Circle(color=BLUE_D) for _ in range(3)]).arrange(RIGHT, buff=1)
        self.play(Transform(shapes, circles))
        self.wait(1)
'''
    }
    
    if example_type not in examples:
        return [TextContent(
            type="text",
            text=f"Unknown example type. Available: {', '.join(examples.keys())}"
        )]
    
    return [TextContent(
        type="text",
        text=f"Example Manim code ({example_type}):\n\n```python\n{examples[example_type]}\n```"
    )]


async def main():
    """Run the MCP server."""
    if not HAS_MCP:
        print("Error: MCP package required. Install with: pip install mcp")
        sys.exit(1)
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
