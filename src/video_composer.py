"""
Video Composer Module

Combines animation videos with voiceover audio and stitches
multiple scenes into a single final video.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

console = Console()


class VideoComposer:
    """Composes final videos by combining animations with voiceovers."""

    def __init__(self):
        self.output_dir = Path(__file__).parent.parent / "output"
        self.output_dir.mkdir(exist_ok=True)
        
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        """Verify FFmpeg is available."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                check=True
            )
        except FileNotFoundError:
            console.print("[red]FFmpeg not found. Please install FFmpeg.[/red]")
            raise RuntimeError("FFmpeg is required for video composition")

    def combine_video_audio(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Optional[Path] = None,
        scene_index: int = 0,
        add_end_pause: float = 2.0,
    ) -> Path:
        """
        Combine a video with an audio track with proper synchronization.
        
        The video will be extended to match audio duration, and optionally
        a pause will be added at the end for section separation.
        
        Args:
            video_path: Path to the animation video
            audio_path: Path to the voiceover audio
            output_path: Where to save the combined video
            scene_index: Scene number for naming
            add_end_pause: Seconds of pause to add at the end (for section breaks)
            
        Returns:
            Path to the combined video
        """
        if output_path is None:
            output_path = self.output_dir / "combined" / f"scene_{scene_index:02d}_combined.mp4"
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        audio_duration = self._get_duration(audio_path)
        video_duration = self._get_duration(video_path)
        
        # Target duration: audio length + end pause for section break
        target_duration = audio_duration + add_end_pause
        
        console.print(f"[dim]Combining scene {scene_index}: video={video_duration:.1f}s, audio={audio_duration:.1f}s, target={target_duration:.1f}s[/dim]")
        
        # Always process video to ensure proper sync and add pause
        temp_extended = output_path.with_suffix(".extended.mp4")
        self._extend_video(video_path, target_duration, temp_extended)
        extended_video_path = temp_extended
        
        # Create audio with silence padding for the end pause
        temp_audio = output_path.with_suffix(".padded.aac")
        self._pad_audio_with_silence(audio_path, add_end_pause, temp_audio)
        
        # Combine video and audio with exact sync
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(extended_video_path),
                "-i", str(temp_audio),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "192k",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-async", "1",  # Audio sync correction
                "-vsync", "cfr",  # Constant frame rate for better sync
                str(output_path)
            ],
            capture_output=True,
            check=True
        )
        
        # Clean up temp files
        extended_video_path.unlink(missing_ok=True)
        temp_audio.unlink(missing_ok=True)
        
        console.print(f"[green]✓ Combined:[/green] {output_path.name}")
        return output_path

    def _get_duration(self, file_path: Path) -> float:
        """Get duration of audio/video file in seconds."""
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path)
            ],
            capture_output=True,
            text=True,
            check=True
        )
        return float(result.stdout.strip())

    def _extend_video(self, video_path: Path, target_duration: float, output_path: Path):
        """Extend video by holding the last frame to match target duration."""
        video_duration = self._get_duration(video_path)
        hold_duration = max(0, target_duration - video_duration + 0.1)
        
        if hold_duration > 0:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-vf", f"tpad=stop_mode=clone:stop_duration={hold_duration}",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "23",
                    "-r", "30",  # Ensure consistent frame rate
                    str(output_path)
                ],
                capture_output=True,
                check=True
            )
        else:
            # Just re-encode with consistent settings if no extension needed
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-t", str(target_duration),
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "23",
                    "-r", "30",
                    str(output_path)
                ],
                capture_output=True,
                check=True
            )

    def _pad_audio_with_silence(self, audio_path: Path, silence_duration: float, output_path: Path):
        """Add silence padding at the end of audio for section breaks."""
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(audio_path),
                "-af", f"apad=pad_dur={silence_duration}",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path)
            ],
            capture_output=True,
            check=True
        )

    def stitch_videos(
        self,
        video_paths: list[Path],
        output_path: Optional[Path] = None,
        add_transitions: bool = False,
    ) -> Path:
        """
        Stitch multiple videos into a single video with proper audio sync.
        
        Args:
            video_paths: List of video paths in order
            output_path: Where to save the final video
            add_transitions: Whether to add fade transitions (disabled by default for better sync)
            
        Returns:
            Path to the final stitched video
        """
        if output_path is None:
            output_path = self.output_dir / "final_video.mp4"
        
        console.print(f"\n[bold blue]Stitching {len(video_paths)} videos...[/bold blue]")
        
        video_paths = [p for p in video_paths if p and p.exists()]
        
        if not video_paths:
            raise ValueError("No valid video paths provided")
        
        if len(video_paths) == 1:
            import shutil
            shutil.copy(video_paths[0], output_path)
            return output_path
        
        # First, normalize all videos to same format for seamless concatenation
        normalized_dir = self.output_dir / "normalized"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        normalized_paths = []
        
        console.print("[dim]Normalizing video formats for seamless stitching...[/dim]")
        for i, vp in enumerate(video_paths):
            norm_path = normalized_dir / f"norm_{i:02d}.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(vp),
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "23",
                    "-r", "30",
                    "-s", "1920x1080",  # Consistent resolution
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ar", "44100",  # Consistent audio sample rate
                    "-ac", "2",  # Stereo audio
                    str(norm_path)
                ],
                capture_output=True,
                check=True
            )
            normalized_paths.append(norm_path)
        
        concat_file = self.output_dir / "concat_list.txt"
        with open(concat_file, "w") as f:
            for vp in normalized_paths:
                f.write(f"file '{vp.absolute()}'\n")
        
        if add_transitions:
            filter_complex = self._build_transition_filter(len(normalized_paths))
            
            cmd = ["ffmpeg", "-y"]
            for vp in normalized_paths:
                cmd.extend(["-i", str(vp)])
            
            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path)
            ])
        else:
            # Use concat demuxer for lossless concatenation with audio sync
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c:v", "copy",
                "-c:a", "copy",
                "-movflags", "+faststart",
                str(output_path)
            ]
        
        try:
            subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            console.print(f"[yellow]Concat failed, retrying with re-encoding...[/yellow]")
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "192k",
                "-r", "30",
                "-ar", "44100",
                str(output_path)
            ]
            subprocess.run(cmd, capture_output=True, check=True)
        
        # Cleanup temp files
        concat_file.unlink(missing_ok=True)
        for np in normalized_paths:
            np.unlink(missing_ok=True)
        
        console.print(f"[green]✓ Final video created:[/green] {output_path}")
        return output_path

    def _build_transition_filter(self, num_videos: int, fade_duration: float = 0.5) -> str:
        """Build FFmpeg filter for crossfade transitions."""
        if num_videos <= 1:
            return "[0:v][0:a]concat=n=1:v=1:a=1[outv][outa]"
        
        filters = []
        
        for i in range(num_videos):
            filters.append(f"[{i}:v]format=yuv420p[v{i}];")
            filters.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}];")
        
        video_concat = "".join(f"[v{i}]" for i in range(num_videos))
        audio_concat = "".join(f"[a{i}]" for i in range(num_videos))
        
        filters.append(f"{video_concat}concat=n={num_videos}:v=1:a=0[outv];")
        filters.append(f"{audio_concat}concat=n={num_videos}:v=0:a=1[outa]")
        
        return "".join(filters)

    def compose_full_video(
        self,
        video_paths: list[Path],
        audio_paths: list[Path],
        output_path: Optional[Path] = None,
        concurrent: bool = True,
        max_workers: int = 4,
        section_pause: float = 2.0,
    ) -> Path:
        """
        Full pipeline: combine each video with audio, then stitch all together.
        
        Args:
            video_paths: List of animation video paths
            audio_paths: List of voiceover audio paths (same order)
            output_path: Where to save the final video
            concurrent: Whether to combine videos concurrently
            max_workers: Number of concurrent workers
            section_pause: Seconds of pause between each section
            
        Returns:
            Path to the final video
        """
        if len(video_paths) != len(audio_paths):
            raise ValueError(f"Mismatch: {len(video_paths)} videos vs {len(audio_paths)} audio files")
        
        console.print(f"\n[bold blue]Composing {len(video_paths)} scenes with {section_pause}s pauses...[/bold blue]")
        
        combined_paths = [None] * len(video_paths)
        total_videos = len(video_paths)
        
        def combine_single(index: int) -> tuple[int, Path]:
            # Add pause to all scenes except the last one
            end_pause = section_pause if index < total_videos - 1 else 0.5
            return index, self.combine_video_audio(
                video_paths[index],
                audio_paths[index],
                scene_index=index,
                add_end_pause=end_pause
            )
        
        if concurrent and len(video_paths) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(combine_single, i): i
                    for i in range(len(video_paths))
                }
                
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("{task.completed}/{task.total}"),
                    console=console,
                ) as progress:
                    task = progress.add_task("Combining videos with audio...", total=len(video_paths))
                    
                    for future in as_completed(futures):
                        index, path = future.result()
                        combined_paths[index] = path
                        progress.advance(task)
        else:
            for i in range(len(video_paths)):
                _, path = combine_single(i)
                combined_paths[i] = path
        
        return self.stitch_videos(combined_paths, output_path, add_transitions=False)


if __name__ == "__main__":
    composer = VideoComposer()
    
    print("VideoComposer ready. Use compose_full_video() to create final video.")
