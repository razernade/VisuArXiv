"""
ElevenLabs Voiceover Module

Generates voiceovers for animation scenes using ElevenLabs TTS API.
"""

import os
from pathlib import Path
from typing import Optional
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

console = Console()


class VoiceoverGenerator:
    """Generates voiceovers using ElevenLabs TTS."""

    VOICE_IDS = {
        "adam": "pNInz6obpgDQGcFmaJgB",
        "rachel": "21m00Tcm4TlvDq8ikWAM",
        "domi": "AZnzlk1XvdvUeBnXmlld",
        "bella": "EXAVITQu4vr4xnSDxMaL",
        "antoni": "ErXwobaYiN019PkySvjV",
        "elli": "MF3mGyEYCl7XYWbV9V6O",
        "josh": "TxGEqnHWrfWFTfGW9XjX",
        "arnold": "VR6AewLTigWG4xSOukaG",
        "sam": "yoZ06aMxZJJ28mfd3POQ",
        "george": "JBFqnCBsd6RMkjVDRZzb",  # Default - warm, educational tone
    }

    def __init__(self, api_key: str = None, voice: str = "george"):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY not found")
        
        self.client = ElevenLabs(api_key=self.api_key)
        self.voice_id = self.VOICE_IDS.get(voice.lower(), voice)
        self.model_id = "eleven_multilingual_v2"
        
        self.output_dir = Path(__file__).parent.parent / "output" / "audio"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_voiceover(
        self,
        text: str,
        output_path: Optional[Path] = None,
        scene_index: int = 0,
        previous_request_ids: list[str] = None,
    ) -> tuple[Path, str]:
        """
        Generate a voiceover for a single scene.
        
        Args:
            text: The narration text
            output_path: Where to save the audio file
            scene_index: Scene number for naming
            previous_request_ids: For request stitching (maintains prosody)
            
        Returns:
            Tuple of (audio_path, request_id)
        """
        if output_path is None:
            output_path = self.output_dir / f"scene_{scene_index:02d}.mp3"
        
        console.print(f"[dim]Generating voiceover for scene {scene_index}...[/dim]")
        
        with self.client.text_to_speech.with_raw_response.convert(
            text=text,
            voice_id=self.voice_id,
            model_id=self.model_id,
            output_format="mp3_44100_128",
            previous_request_ids=previous_request_ids or [],
            voice_settings=VoiceSettings(
                stability=0.5,
                similarity_boost=0.75,
                style=0.0,
                use_speaker_boost=True,
                speed=0.95,  # Slightly slower for educational content
            ),
        ) as response:
            request_id = response._response.headers.get("request-id")
            
            with open(output_path, "wb") as f:
                for chunk in response.data:
                    if chunk:
                        f.write(chunk)
        
        console.print(f"[green]✓ Voiceover saved:[/green] {output_path.name}")
        return output_path, request_id

    def generate_all_voiceovers(
        self,
        scenes: list[dict],
        concurrent: bool = True,
        max_workers: int = 3,
    ) -> list[Path]:
        """
        Generate voiceovers for all scenes.
        
        Args:
            scenes: List of scene dictionaries with 'narration' field
            concurrent: Whether to generate concurrently
            max_workers: Number of concurrent workers
            
        Returns:
            List of audio file paths in order
        """
        console.print(f"\n[bold blue]Generating {len(scenes)} voiceovers...[/bold blue]")
        
        if not concurrent:
            return self._generate_sequential(scenes)
        else:
            return self._generate_concurrent(scenes, max_workers)

    def _generate_sequential(self, scenes: list[dict]) -> list[Path]:
        """Generate voiceovers sequentially with request stitching."""
        audio_paths = []
        request_ids = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Generating voiceovers...", total=len(scenes))
            
            for i, scene in enumerate(scenes):
                narration = scene.get("narration", "")
                if not narration:
                    narration = scene.get("key_insight", f"Scene {i+1}")
                
                audio_path, request_id = self.generate_voiceover(
                    text=narration,
                    scene_index=i,
                    previous_request_ids=request_ids[-3:] if request_ids else None,
                )
                
                audio_paths.append(audio_path)
                request_ids.append(request_id)
                progress.advance(task)
        
        return audio_paths

    def _generate_concurrent(self, scenes: list[dict], max_workers: int) -> list[Path]:
        """Generate voiceovers concurrently (faster but no stitching)."""
        audio_paths = [None] * len(scenes)
        
        def generate_single(index: int, scene: dict) -> tuple[int, Path]:
            narration = scene.get("narration", "")
            if not narration:
                narration = scene.get("key_insight", f"Scene {index+1}")
            
            audio_path, _ = self.generate_voiceover(
                text=narration,
                scene_index=index,
            )
            return index, audio_path
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Generating voiceovers (concurrent)...", total=len(scenes))
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(generate_single, i, scene): i 
                    for i, scene in enumerate(scenes)
                }
                
                for future in as_completed(futures):
                    index, audio_path = future.result()
                    audio_paths[index] = audio_path
                    progress.advance(task)
        
        return audio_paths


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    generator = VoiceoverGenerator()
    
    test_scenes = [
        {"narration": "Welcome to this visualization of the Attention mechanism."},
        {"narration": "The key insight is that attention allows the model to focus on relevant parts of the input."},
        {"narration": "Thank you for watching this explanation."},
    ]
    
    paths = generator.generate_all_voiceovers(test_scenes, concurrent=False)
    print(f"Generated {len(paths)} audio files")
