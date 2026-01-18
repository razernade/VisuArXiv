"""
Gemini Deep Research Module

Uses Google's Gemini Deep Research Agent via Interactions API
to analyze research papers and extract structured, visualizable concepts.
"""

import os
import time
import json
from pathlib import Path
from google import genai
from google.genai import types
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

console = Console()


class GeminiResearcher:
    """Handles deep research analysis of academic papers using Gemini."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")
        
        self.client = genai.Client(api_key=self.api_key)
        self.model = "gemini-3-flash-preview"
        self.research_agent = "deep-research-pro-preview-12-2025"
        
        self.research_prompt = self._load_research_prompt()

    def _load_research_prompt(self) -> str:
        prompt_path = Path(__file__).parent.parent / "research_prompt.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return "Analyze this research paper and extract key visualizable concepts as JSON."

    def upload_file(self, file_path: str) -> types.File:
        """Upload a PDF file to Gemini."""
        console.print(f"[blue]Uploading file:[/blue] {file_path}")
        
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        uploaded_file = self.client.files.upload(file=file_path)
        console.print(f"[green]✓ File uploaded:[/green] {uploaded_file.name}")
        
        return uploaded_file

    def analyze_paper(self, file_path: str, use_deep_research: bool = True) -> dict:
        """
        Analyze a research paper and extract structured visualization data.
        
        Args:
            file_path: Path to the PDF file
            use_deep_research: If True, uses Deep Research agent (slower but thorough)
        
        Returns:
            Structured JSON with scenes for visualization
        """
        uploaded_file = self.upload_file(file_path)
        
        if use_deep_research:
            return self._deep_research_analysis(uploaded_file)
        else:
            return self._standard_analysis(uploaded_file)

    def _deep_research_analysis(self, uploaded_file: types.File) -> dict:
        """Use Gemini Deep Research Agent via Interactions API."""
        console.print("[yellow]Starting Deep Research Agent...[/yellow]")
        console.print("[dim]This may take 2-5 minutes as the agent thoroughly analyzes the paper.[/dim]")
        
        # First, extract paper summary using standard model (Deep Research doesn't support file uploads)
        console.print("[blue]Step 1: Extracting paper content with standard model...[/blue]")
        extraction_prompt = """
Analyze this research paper and provide a detailed summary including:
1. Paper title and authors
2. Main topic and research area
3. Key concepts, theorems, and mathematical formulations
4. Core algorithms or methods described
5. Important equations and their meanings
6. Main findings and contributions

Be thorough and include all technical details that would be relevant for creating educational visualizations.
"""
        
        extraction_response = self.client.models.generate_content(
            model=self.model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=uploaded_file.uri,
                            mime_type=uploaded_file.mime_type,
                        ),
                        types.Part.from_text(text=extraction_prompt),
                    ],
                ),
            ],
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,
            ),
        )
        
        paper_summary = extraction_response.text
        console.print("[green]✓ Paper content extracted[/green]")
        
        # Now use Deep Research to find additional context and visualizable concepts
        console.print("[blue]Step 2: Deep Research for additional context...[/blue]")
        
        prompt = f"""
{self.research_prompt}

I have a research paper with the following content:

---
{paper_summary}
---

Based on this paper, research and extract all key concepts that can be visualized using mathematical animations. 
Search for additional context, intuitions, and visual explanations for the concepts mentioned.

Focus on:
1. Core theorems and their intuitions
2. Mathematical relationships and equations  
3. Step-by-step processes or algorithms
4. Visual metaphors that explain abstract concepts

Return ONLY a valid JSON object following the schema in my instructions.
"""

        try:
            initial_interaction = self.client.interactions.create(
                input=prompt,
                agent=self.research_agent,
                background=True,
            )
            
            console.print(f"[dim]Interaction ID: {initial_interaction.id}[/dim]")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.fields[status]}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Deep Research in progress...", 
                    total=None,
                    status="starting"
                )
                
                poll_count = 0
                max_polls = 120
                
                while poll_count < max_polls:
                    interaction = self.client.interactions.get(initial_interaction.id)
                    status = interaction.status
                    
                    progress.update(task, status=status)
                    
                    if status == "completed":
                        progress.update(task, status="[green]completed[/green]")
                        
                        if interaction.outputs:
                            result_text = None
                            for output in interaction.outputs:
                                if hasattr(output, 'parts'):
                                    for part in output.parts:
                                        if hasattr(part, 'text') and part.text:
                                            result_text = part.text
                                elif hasattr(output, 'text'):
                                    result_text = output.text
                            
                            if result_text:
                                return self._parse_response(result_text)
                        
                        console.print("[red]No output found in completed interaction[/red]")
                        return self._standard_analysis(uploaded_file)
                        
                    elif status in ["failed", "cancelled"]:
                        progress.update(task, status=f"[red]{status}[/red]")
                        console.print(f"[red]Deep Research {status}[/red]")
                        return self._standard_analysis(uploaded_file)
                    
                    time.sleep(5)
                    poll_count += 1
                
                console.print("[red]Deep Research timed out after 10 minutes[/red]")
                return self._standard_analysis(uploaded_file)
            
        except Exception as e:
            console.print(f"[red]Deep Research failed: {e}[/red]")
            console.print("[yellow]Falling back to standard analysis...[/yellow]")
            return self._standard_analysis(uploaded_file)

    def _standard_analysis(self, uploaded_file: types.File) -> dict:
        """Use standard Gemini model for faster analysis."""
        console.print("[blue]Running standard analysis with Gemini 2.5 Pro...[/blue]")
        
        prompt = f"""
{self.research_prompt}

Analyze the uploaded research paper. Extract key concepts that can be visualized.
Return ONLY a valid JSON object following the schema in my instructions.
"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=uploaded_file.uri,
                            mime_type=uploaded_file.mime_type,
                        ),
                        types.Part.from_text(text=prompt),
                    ],
                ),
            ],
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )
        
        return self._parse_response(response.text)

    def _parse_response(self, response_text: str) -> dict:
        """Parse the JSON response from Gemini."""
        text = response_text.strip()
        
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        
        text = text.strip()
        
        try:
            result = json.loads(text)
            console.print(f"[green]✓ Successfully extracted {len(result.get('scenes', []))} scenes[/green]")
            return result
        except json.JSONDecodeError as e:
            console.print(f"[red]Failed to parse JSON response: {e}[/red]")
            console.print("[dim]Raw response (first 500 chars):[/dim]")
            console.print(response_text[:500])
            return {
                "error": "Failed to parse response",
                "raw_response": response_text,
                "scenes": []
            }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    researcher = GeminiResearcher()
    
    import sys
    if len(sys.argv) > 1:
        use_deep = "--fast" not in sys.argv
        pdf_path = [arg for arg in sys.argv[1:] if not arg.startswith("--")][0]
        result = researcher.analyze_paper(pdf_path, use_deep_research=use_deep)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python gemini_researcher.py <path_to_pdf> [--fast]")
