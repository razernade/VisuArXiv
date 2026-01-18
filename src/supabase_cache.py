"""
Supabase Cache Module

Caches generated videos in Supabase storage for research papers.
If a video was previously generated for a paper, it can be retrieved
directly without regenerating.
"""

import os
import hashlib
import json
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

from rich.console import Console

console = Console()

# Supabase configuration
SUPABASE_URL = "https://wnsgwijukvnfcpeuiugk.supabase.co/"
# Use the SECRET key for storage operations (bypasses RLS)
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = "research-videos"
# Note: For full write access, you may need to use the service role key
# or configure RLS policies in Supabase for the storage bucket

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    console.print("[yellow]Warning: supabase-py not installed. Video caching disabled.[/yellow]")


class SupabaseVideoCache:
    """Cache for storing and retrieving generated videos in Supabase."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        bucket_name: str = SUPABASE_BUCKET,
    ):
        self.url = supabase_url or os.getenv("SUPABASE_URL") or SUPABASE_URL
        self.key = supabase_key or os.getenv("SUPABASE_KEY") or SUPABASE_KEY
        self.bucket_name = bucket_name
        self.client: Optional[Client] = None
        
        if SUPABASE_AVAILABLE:
            try:
                self.client = create_client(self.url, self.key)
                self._ensure_bucket_exists()
                console.print("[green]✓ Supabase cache initialized[/green]")
            except Exception as e:
                console.print(f"[yellow]Warning: Supabase connection failed: {e}[/yellow]")
                self.client = None

    def _ensure_bucket_exists(self):
        """Ensure the storage bucket exists, create if not."""
        if not self.client:
            return
        
        try:
            # List buckets to check if ours exists
            buckets = self.client.storage.list_buckets()
            bucket_names = [b.name for b in buckets]
            
            if self.bucket_name not in bucket_names:
                # Try to create the bucket with public access
                try:
                    self.client.storage.create_bucket(
                        self.bucket_name,
                        options={"public": True}
                    )
                    console.print(f"[green]✓ Created storage bucket: {self.bucket_name}[/green]")
                except Exception as create_err:
                    # Bucket creation may fail due to RLS, but bucket might exist
                    console.print(f"[yellow]Note: Could not create bucket (may need to create manually in Supabase dashboard): {create_err}[/yellow]")
        except Exception as e:
            # If we can't list buckets, the bucket may still exist and be usable
            console.print(f"[dim]Note: Could not verify bucket (will attempt operations anyway): {e}[/dim]")

    def _generate_paper_hash(self, paper_identifier: str) -> str:
        """Generate a unique hash for a paper based on its identifier (title, arxiv_id, or filename)."""
        # Normalize the identifier
        normalized = paper_identifier.lower().strip()
        # Remove common variations
        for suffix in [".pdf", ".arxiv", ".abs"]:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]
        
        # Create MD5 hash (sufficient for cache key)
        return hashlib.md5(normalized.encode()).hexdigest()

    def _get_video_path(self, paper_hash: str) -> str:
        """Get the storage path for a video."""
        return f"videos/{paper_hash}/final_video.mp4"

    def _get_metadata_path(self, paper_hash: str) -> str:
        """Get the storage path for metadata."""
        return f"videos/{paper_hash}/metadata.json"

    def check_cache(self, paper_identifier: str) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Check if a video exists in cache for the given paper.
        
        Args:
            paper_identifier: Paper title, arxiv ID, or filename
            
        Returns:
            Tuple of (exists, video_url, metadata)
        """
        if not self.client:
            return False, None, None
        
        paper_hash = self._generate_paper_hash(paper_identifier)
        video_path = self._get_video_path(paper_hash)
        metadata_path = self._get_metadata_path(paper_hash)
        
        try:
            # Check if video exists by trying to get its public URL
            video_url = self.client.storage.from_(self.bucket_name).get_public_url(video_path)
            
            # Try to fetch metadata
            metadata = None
            try:
                metadata_response = self.client.storage.from_(self.bucket_name).download(metadata_path)
                if metadata_response:
                    metadata = json.loads(metadata_response.decode('utf-8'))
            except Exception:
                pass
            
            # Verify the video actually exists by making a HEAD request
            import urllib.request
            import urllib.error
            
            req = urllib.request.Request(video_url, method='HEAD')
            req.add_header('User-Agent', 'VisuArXiv/1.0')
            try:
                response = urllib.request.urlopen(req, timeout=10)
                if response.status == 200:
                    console.print(f"[green]✓ Cache hit for paper: {paper_identifier[:50]}...[/green]")
                    return True, video_url, metadata
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    console.print(f"[dim]Cache check HTTP error: {e.code}[/dim]")
                return False, None, None
            except Exception as e:
                console.print(f"[dim]Cache check failed: {e}[/dim]")
                return False, None, None
                
        except Exception as e:
            console.print(f"[dim]Cache check error: {e}[/dim]")
            return False, None, None
        
        return False, None, None

    def upload_video(
        self,
        video_path: Path,
        paper_identifier: str,
        metadata: Optional[dict] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Upload a generated video to Supabase cache.
        
        Args:
            video_path: Local path to the video file
            paper_identifier: Paper title, arxiv ID, or filename
            metadata: Optional metadata about the generation
            
        Returns:
            Tuple of (success, video_url)
        """
        if not self.client:
            console.print("[yellow]Supabase client not available, skipping cache upload[/yellow]")
            return False, None
        
        if not video_path.exists():
            console.print(f"[red]Video file not found: {video_path}[/red]")
            return False, None
        
        paper_hash = self._generate_paper_hash(paper_identifier)
        storage_video_path = self._get_video_path(paper_hash)
        storage_metadata_path = self._get_metadata_path(paper_hash)
        
        try:
            # Upload video file
            console.print(f"[dim]Uploading video ({video_path.stat().st_size / 1024 / 1024:.1f} MB)...[/dim]")
            
            with open(video_path, "rb") as f:
                video_data = f.read()
            
            # Delete existing file if present (upsert)
            try:
                self.client.storage.from_(self.bucket_name).remove([storage_video_path])
            except Exception:
                pass
            
            upload_response = self.client.storage.from_(self.bucket_name).upload(
                storage_video_path,
                video_data,
                file_options={"content-type": "video/mp4", "upsert": "true"}
            )
            
            # Upload metadata
            if metadata is None:
                metadata = {}
            
            metadata.update({
                "paper_identifier": paper_identifier,
                "paper_hash": paper_hash,
                "uploaded_at": datetime.now().isoformat(),
                "original_filename": video_path.name,
                "file_size_bytes": video_path.stat().st_size,
            })
            
            try:
                self.client.storage.from_(self.bucket_name).remove([storage_metadata_path])
            except Exception:
                pass
            
            self.client.storage.from_(self.bucket_name).upload(
                storage_metadata_path,
                json.dumps(metadata, indent=2).encode('utf-8'),
                file_options={"content-type": "application/json", "upsert": "true"}
            )
            
            # Get public URL
            video_url = self.client.storage.from_(self.bucket_name).get_public_url(storage_video_path)
            
            console.print(f"[green]✓ Video cached in Supabase[/green]")
            console.print(f"[dim]URL: {video_url}[/dim]")
            
            return True, video_url
            
        except Exception as e:
            error_msg = str(e)
            if "row-level security" in error_msg.lower() or "unauthorized" in error_msg.lower():
                console.print(f"[yellow]Note: Supabase upload requires proper RLS configuration or service role key[/yellow]")
                console.print(f"[dim]Please create the bucket '{self.bucket_name}' manually in Supabase dashboard with public access[/dim]")
            else:
                console.print(f"[red]Failed to upload to Supabase: {e}[/red]")
            return False, None

    def download_cached_video(
        self,
        paper_identifier: str,
        output_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        """
        Download a cached video to local storage.
        
        Args:
            paper_identifier: Paper title, arxiv ID, or filename
            output_dir: Directory to save the video (defaults to output/)
            
        Returns:
            Path to downloaded video or None if not found
        """
        if not self.client:
            return None
        
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "output"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        paper_hash = self._generate_paper_hash(paper_identifier)
        storage_path = self._get_video_path(paper_hash)
        local_path = output_dir / f"cached_{paper_hash}.mp4"
        
        try:
            # Download video
            video_data = self.client.storage.from_(self.bucket_name).download(storage_path)
            
            if video_data:
                with open(local_path, "wb") as f:
                    f.write(video_data)
                
                console.print(f"[green]✓ Downloaded cached video: {local_path}[/green]")
                return local_path
            
        except Exception as e:
            console.print(f"[dim]Could not download cached video: {e}[/dim]")
        
        return None

    def get_cache_url(self, paper_identifier: str) -> Optional[str]:
        """
        Get the public URL for a cached video without downloading.
        
        Args:
            paper_identifier: Paper title, arxiv ID, or filename
            
        Returns:
            Public URL or None if not cached
        """
        exists, url, _ = self.check_cache(paper_identifier)
        return url if exists else None

    def list_cached_papers(self) -> list[dict]:
        """List all cached papers with their metadata."""
        if not self.client:
            return []
        
        try:
            files = self.client.storage.from_(self.bucket_name).list("videos")
            papers = []
            
            for folder in files:
                if folder.get("name"):
                    metadata_path = f"videos/{folder['name']}/metadata.json"
                    try:
                        metadata_data = self.client.storage.from_(self.bucket_name).download(metadata_path)
                        if metadata_data:
                            metadata = json.loads(metadata_data.decode('utf-8'))
                            papers.append(metadata)
                    except:
                        papers.append({"paper_hash": folder["name"]})
            
            return papers
            
        except Exception as e:
            console.print(f"[dim]Could not list cached papers: {e}[/dim]")
            return []


# Singleton instance for easy access
_cache_instance: Optional[SupabaseVideoCache] = None


def get_video_cache() -> SupabaseVideoCache:
    """Get the singleton video cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SupabaseVideoCache()
    return _cache_instance


if __name__ == "__main__":
    # Test the cache
    cache = get_video_cache()
    
    # Test check cache
    exists, url, metadata = cache.check_cache("Attention Is All You Need")
    print(f"Cached: {exists}, URL: {url}")
    
    # List cached papers
    papers = cache.list_cached_papers()
    print(f"Cached papers: {len(papers)}")
