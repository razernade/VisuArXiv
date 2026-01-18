import arxiv
import os
import re
from pathlib import Path

def search_arxiv(query, max_results=10):
    """
    Search arXiv for papers matching the query.
    Returns a list of dicts with paper details.
    """
    # Check if query looks like an arXiv ID (e.g., 1706.03762 or 1706.03762v1)
    arxiv_id_pattern = r'^\d{4}\.\d{4,5}(v\d+)?$'
    
    if re.match(arxiv_id_pattern, query.strip()):
        # Direct ID lookup
        search = arxiv.Search(id_list=[query.strip()])
    else:
        # Build a query that searches each word in the title
        # This works better for finding exact paper titles
        words = query.strip().split()
        if len(words) > 1:
            # Search for all words in title (best for paper titles)
            title_query = " ".join([f'ti:{word}' for word in words if len(word) > 2])
            # Also allow general search as fallback
            search_query = f'({title_query}) OR all:"{query}"'
        else:
            search_query = f'ti:{query} OR all:{query}'
        
        search = arxiv.Search(
            query=search_query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance
        )
    
    results = []
    for result in search.results():
        results.append({
            "title": result.title,
            "authors": ", ".join([a.name for a in result.authors]),
            "summary": result.summary.replace("\n", " "),
            "pdf_url": result.pdf_url,
            "entry_id": result.entry_id,
            "published": result.published.strftime("%Y-%m-%d")
        })
    return results

def download_arxiv_pdf(pdf_url, output_dir="temp_papers"):
    """
    Download an arXiv paper to a local directory.
    Returns the path to the downloaded file.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    paper_id = pdf_url.split("/")[-1]
    if "v" in paper_id:
         # simple check to avoid weird filenames if version is included
        pass
    
    filename = f"{paper_id}.pdf"
    filepath = os.path.join(output_dir, filename)
    
    if os.path.exists(filepath):
        return filepath
        
    import requests
    response = requests.get(pdf_url)
    if response.status_code == 200:
        with open(filepath, "wb") as f:
            f.write(response.content)
        return filepath
    else:
        raise Exception(f"Failed to download PDF: {response.status_code}")
