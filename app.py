"""
Web Interface for Research-to-Animation Pipeline

A professional, elegant Gradio-based UI for discovering research papers
and converting them into engaging video content.
"""

import os
import json
import tempfile
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Import core modules
from src.gemini_researcher import GeminiResearcher
from src.claude_mcp_animator import ClaudeMCPAnimator
from src.arxiv_loader import search_arxiv, download_arxiv_pdf
from src.voiceover import VoiceoverGenerator
from src.video_composer import VideoComposer
from src.supabase_cache import get_video_cache

# --- UI Configuration & Theme ---
import gradio as gr

theme = gr.themes.Default(
    primary_hue="orange",
    secondary_hue="slate",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"],
).set(
    body_background_fill="#000000",
    block_background_fill="#000000",
    block_border_width="1px",
    block_border_color="#111111",
    block_shadow="none",
    button_primary_background_fill="#ffffff",
    button_primary_background_fill_hover="#eeeeee",
    button_primary_text_color="#000000",
    input_background_fill="#0a0a0a",
    input_border_color="#222222",
)

custom_css = """
.container { max-width: 1200px; margin: auto; padding: 1rem 1rem; }
.header { text-align: left; margin-bottom: 1.5rem; border-left: 2px solid #c27e47; padding-left: 1.5rem; }
.header h1 { font-family: 'JetBrains Mono', monospace; font-size: 2rem; font-weight: 500; letter-spacing: -1px; color: #ffffff; margin: 0; }
.header p { font-size: 0.8rem; color: #c27e47; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; letter-spacing: 3px; margin-top: 0.25rem; }

.gr-button-primary { 
    border-radius: 8px !important; 
    text-transform: uppercase; 
    letter-spacing: 1px; 
    font-weight: 600 !important;
    height: 100%;
}

.gr-tabs { border: none !important; background: transparent !important; margin-bottom: 0 !important; }
.gr-tab-nav { border-bottom: 1px solid #222 !important; margin-bottom: 1rem; }
.gr-tab-nav button { font-family: 'JetBrains Mono', monospace; text-transform: uppercase; font-size: 0.8rem !important; color: #666 !important; }
.gr-tab-nav button.selected { border-bottom: 2px solid #c27e47 !important; background: transparent !important; color: #c27e47 !important; }

.gr-form { border: none !important; background: transparent !important; }
.gr-box { border-radius: 0px !important; border: 1px solid #111111 !important; }
.gr-input { border-radius: 4px !important; font-family: 'JetBrains Mono', monospace; border: 1px solid #333 !important; background: #0a0a0a !important; }

/* Custom Search Results List */
.search-result-item {
    background: #080808;
    border: 1px solid #222;
    border-radius: 6px;
    padding: 1rem;
    margin-bottom: 0.5rem;
    cursor: pointer;
    transition: all 0.15s ease;
    text-align: left;
    position: relative;
}
.search-result-item:hover {
    border-color: #555;
    background: #111;
}
.search-result-item.selected {
    border-color: #c27e47;
    background: #111;
    border-left: 3px solid #c27e47;
}
.result-title {
    color: #fff;
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 0.3rem;
    font-family: 'JetBrains Mono', monospace;
}
.result-meta {
    color: #888;
    font-size: 0.8rem;
    margin-bottom: 0.2rem;
    font-family: 'JetBrains Mono', monospace;
}
.summary-box {
    display: none; /* Hidden by default */
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid #333;
    color: #ccc;
    font-size: 0.9rem;
    line-height: 1.5;
}

/* Hide the radio circle for a cleaner 'card' look */
.gr-radio input[type="radio"] {
    display: none !important;
}

.gr-markdown h3 { font-family: 'JetBrains Mono', monospace; text-transform: uppercase; letter-spacing: 2px; color: #c27e47; font-size: 0.9rem; margin-bottom: 1rem; }

/* Deep Research Checkbox - white border */
.deep-research-checkbox input[type="checkbox"] {
    border: 2px solid #fff !important;
    accent-color: #c27e47 !important;
}

/* URL field with inline copy button */
#url_storage {
    position: relative !important;
}
#url_storage .wrap {
    position: relative !important;
    display: flex !important;
    align-items: center !important;
}
#url_storage textarea,
#url_storage input {
    padding-right: 130px !important;
}
.inline-copy-btn {
    position: absolute !important;
    right: 8px !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    background: rgba(194, 126, 71, 0.15) !important;
    border: none !important;
    color: #c27e47 !important;
    padding: 8px 16px !important;
    border-radius: 20px !important;
    cursor: pointer !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
    transition: all 0.15s ease-in-out !important;
    z-index: 10 !important;
    font-family: 'JetBrains Mono', monospace !important;
    text-transform: none !important;
    white-space: nowrap !important;
    line-height: 1 !important;
    height: auto !important;
    min-width: auto !important;
}
.inline-copy-btn:hover {
    background: rgba(194, 126, 71, 0.3) !important;
}
.inline-copy-btn .copy-icon {
    width: 14px !important;
    height: 14px !important;
    flex-shrink: 0 !important;
}
.copy-tooltip {
    position: absolute !important;
    bottom: calc(100% + 10px) !important;
    left: 50% !important;
    transform: translateX(-50%) translateY(8px) !important;
    background: #111111 !important;
    color: #ffffff !important;
    padding: 8px 16px !important;
    border-radius: 8px !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    white-space: nowrap !important;
    opacity: 0 !important;
    pointer-events: none !important;
    transition: all 0.15s ease-in-out !important;
    border: 1px solid #333 !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.6) !important;
}
.copy-tooltip.show {
    opacity: 1 !important;
    transform: translateX(-50%) translateY(0) !important;
}
"""

# --- Logic ---

def format_results_html(results):
    if not results:
        return "<div style='color: #666; padding: 1rem;'>No results found.</div>"
    
    html = ""
    for r in results:
        # Escape quotes for data attribute
        safe_url = r['pdf_url'].replace('"', '&quot;')
        safe_summary = r['summary'].replace('"', '&quot;').replace('\n', ' ')
        
        html += f"""
        <div class="search-result-item" data-url="{safe_url}">
            <div class="result-title">{r['title']}</div>
            <div class="result-meta">By: {r['authors']}</div>
            <div class="result-meta">Date: {r['published']}</div>
            <div class="summary-box">
                <strong>Abstract:</strong><br>
                {r['summary']}
            </div>
        </div>
        """
    return html

def perform_arxiv_search(query, sort_by="relevance"):
    if not query:
        return [], []
    results = search_arxiv(query)
    
    # Sort results based on user preference
    results = sort_results(results, sort_by)
    
    # Return formatted HTML and raw data
    html_content = format_results_html(results)
    return html_content, results


def sort_results(results, sort_by):
    """Sort search results by the specified criteria."""
    if not results:
        return results
    
    if sort_by == "alphabetical":
        return sorted(results, key=lambda x: x['title'].lower())
    elif sort_by == "recent":
        return sorted(results, key=lambda x: x['published'], reverse=True)
    elif sort_by == "oldest":
        return sorted(results, key=lambda x: x['published'])
    else:  # relevance (default) - keep original order from arXiv
        return results

def process_pipeline(input_type, pdf_file, arxiv_url, use_deep):
    """
    Unified pipeline processor with caching and concurrent generation.
    """
    target_pdf_path = None
    paper_identifier = None
    
    if input_type == "arXiv Search":
        if not arxiv_url:
            return "Please select a paper from the search results first.", None, None
        yield f"⬇️ Downloading paper from {arxiv_url}...", None, None
        try:
            target_pdf_path = download_arxiv_pdf(arxiv_url)
            # Extract arxiv ID from URL for caching
            paper_identifier = Path(target_pdf_path).stem
            yield f"✅ Downloaded to {target_pdf_path}", None, None
        except Exception as e:
            yield f"❌ Download failed: {str(e)}", None, None
            return
    else:
        if pdf_file is None:
            yield "Please upload a PDF file.", None, None
            return
        target_pdf_path = pdf_file
        paper_identifier = Path(target_pdf_path if isinstance(target_pdf_path, str) else target_pdf_path.name).stem

    # Step 0: Check Supabase cache first
    yield "🔍 Checking cache for existing video...", None, None
    
    cache = get_video_cache()
    cached, cached_url, cached_metadata = cache.check_cache(paper_identifier)
    
    if cached and cached_url:
        yield f"✅ Found cached video!", None, None
        
        # Download the cached video for local playback
        output_dir = Path(__file__).parent / "output"
        local_cached = cache.download_cached_video(paper_identifier, output_dir)
        
        cached_title = cached_metadata.get("paper_title", paper_identifier) if cached_metadata else paper_identifier
        final_message = f"✅ Retrieved cached video for: {cached_title}\n\n"
        final_message += f"📊 This video was previously generated and cached.\n"
        final_message += f"🔗 Direct URL: {cached_url}"
        
        research_data = cached_metadata or {"paper_title": paper_identifier, "cached": True}
        yield final_message, str(local_cached) if local_cached else cached_url, json.dumps(research_data, indent=2)
        return

    # Core Logic - no cache hit, generate new video
    researcher = GeminiResearcher()
    animator = ClaudeMCPAnimator()
    
    yield "🔎 Analyzing research paper...", None, None
    
    try:
        # Use filename as identifier if it's a path string, else use name attr (gradio file obj)
        file_path_str = target_pdf_path if isinstance(target_pdf_path, str) else target_pdf_path.name
        research_data = researcher.analyze_paper(file_path_str, use_deep)
    except Exception as e:
        yield f"❌ Research analysis failed: {str(e)}", None, None
        return
    
    if "error" in research_data or not research_data.get("scenes"):
        yield f"❌ Failed to extract scenes: {research_data.get('error', 'Unknown error')}", None, None
        return
    
    scenes = research_data.get("scenes", [])
    scene_summary = f"📊 Distilled {len(scenes)} key visual segments:\n\n"
    for i, scene in enumerate(scenes):
        scene_summary += f"**[{i+1}] {scene.get('title', 'Untitled')}**\n"
        scene_summary += f"{scene.get('key_insight', 'No insight')[:120]}...\n\n"
        
    yield scene_summary + "\n\n🎬 Synthesizing animations concurrently...", None, json.dumps(research_data, indent=2)
    
    # Initialize components for full pipeline
    voiceover = VoiceoverGenerator()
    composer = VideoComposer()
    
    # Render all scenes CONCURRENTLY for faster generation
    scenes_to_render = scenes
    
    yield scene_summary + f"\n\n🎬 Generating {len(scenes_to_render)} animations in parallel...", None, json.dumps(research_data, indent=2)
    
    # Use concurrent animation generation
    animation_results = animator.generate_animations_concurrent(scenes_to_render, max_workers=3)
    
    video_paths = [Path(vp) for _, vp in animation_results if vp is not None]
    
    if video_paths:
        # Generate voiceovers for successful scenes concurrently
        yield scene_summary + "\n\n🎤 Generating voiceovers concurrently...", None, json.dumps(research_data, indent=2)
        
        successful_scenes = [scenes[i] for i, (_, vp) in enumerate(animation_results) if vp]
        audio_paths = voiceover.generate_all_voiceovers(
            successful_scenes,
            concurrent=True,
            max_workers=3,
        )
        
        # Compose final video with all scenes stitched together and audio
        # Use section_pause to add pauses between scenes
        yield scene_summary + "\n\n🎞️ Composing final video with 2s pauses between scenes...", None, json.dumps(research_data, indent=2)
        
        final_video = composer.compose_full_video(
            video_paths,
            audio_paths,
            concurrent=True,
            max_workers=3,
            section_pause=2.0,  # 2 second pause between scenes
        )
        
        # Upload to Supabase cache
        yield scene_summary + "\n\n☁️ Caching video for future queries...", None, json.dumps(research_data, indent=2)
        
        cache_metadata = {
            "paper_title": research_data.get("paper_title", "Unknown"),
            "total_scenes": len(animation_results),
            "successful_renders": len(video_paths),
        }
        
        success, video_url = cache.upload_video(
            final_video,
            paper_identifier,
            metadata=cache_metadata,
        )
        
        final_message = f"✅ Complete video generated: {len(video_paths)} scenes with voiceover.\n\n"
        if success and video_url:
            final_message += f"☁️ Video cached for future queries!\n🔗 URL: {video_url}\n\n"
        final_message += scene_summary
        yield final_message, str(final_video), json.dumps(research_data, indent=2)
    else:
        yield "⚠️ Process complete but output generation failed.", None, json.dumps(research_data, indent=2)


# --- Application ---

with gr.Blocks(theme=theme, css=custom_css, title="VisuArXiv") as app:
    
    with gr.Column(elem_classes="container"):
        
        # Header
        gr.HTML("""
        <div class="header">
            <h1>VisuArXiv</h1>
            <p>Visualise Concepts from Research Papers</p>
        </div>
        """)
        
        # State
        selected_arxiv_url = gr.State("")
        search_results_state = gr.State([])

        # Input Section
        with gr.Tabs() as tabs:
            
            # Tab 1: ArXiv Search
            with gr.TabItem("Search ArXiv", id="tab_arxiv"):
                
                with gr.Row(equal_height=True, elem_id="custom-search-row"):
                    search_query = gr.Textbox(
                        show_label=False,
                        placeholder="Search for research papers...",
                        scale=5,
                        container=False
                    )
                    search_btn = gr.Button("Search", variant="primary", scale=1, min_width=100)
                    
                    sort_dropdown = gr.Dropdown(
                        choices=[
                            ("Relevance", "relevance"),
                            ("Alphabetical (A-Z)", "alphabetical"),
                            ("Most Recent", "recent"),
                            ("Oldest First", "oldest")
                        ],
                        value="relevance",
                        show_label=False,
                        container=False,
                        scale=2,
                        interactive=True
                    )
                
                # HTML Container for custom list
                search_results_container = gr.HTML(label="Search Results", elem_id="search_results_wrapper")
                
                # Storage for selection logic with inline copy button
                # JS will write to this - must be interactive for change events to work
                url_storage = gr.Textbox(label="Selected Paper URL", elem_id="url_storage", interactive=True, visible=True)


            # Tab 2: Upload PDF
            with gr.TabItem("Upload Research PDF", id="tab_upload"):
                file_upload = gr.File(label="Upload Local PDF File", file_types=[".pdf"])

        # Configuration & Action
        with gr.Group():
            gr.Markdown("### Generation Settings")
            use_deep = gr.Checkbox(
                label="Enable Deep Research (Recommended for complex papers)", 
                value=False,
                elem_classes="deep-research-checkbox"
            )
                
            generate_btn = gr.Button("GENERATE VIDEO", variant="primary", size="lg")

        # Output Section - Video on top, status below
        with gr.Column():
            video_player = gr.Video(label="Final Animation", interactive=False)
            status_log = gr.Markdown("### System Status\nReady.")
            # Hidden JSON for internal state
            json_debug_view = gr.JSON(visible=False)

    # --- Event Handlers ---

    def handle_search(query, sort_by):
        html_content, raw_data = perform_arxiv_search(query, sort_by)
        return html_content, raw_data, ""

    search_btn.click(
        fn=handle_search,
        inputs=[search_query, sort_dropdown],
        outputs=[search_results_container, search_results_state, selected_arxiv_url]
    )

    search_query.submit(
        fn=handle_search,
        inputs=[search_query, sort_dropdown],
        outputs=[search_results_container, search_results_state, selected_arxiv_url]
    )
    
    # Re-sort when dropdown changes (if there are existing results)
    def handle_sort_change(query, sort_by, current_results):
        if not current_results:
            return "", [] # Return empty HTML
        html_content = format_results_html(current_results) # Re-render HTML from state if needed, or re-search?
        # Ideally we resort 'current_results' locally without re-fetching
        sorted_res = sort_results(current_results, sort_by)
        return format_results_html(sorted_res), sorted_res

    sort_dropdown.change(
        fn=handle_sort_change,
        inputs=[search_query, sort_dropdown, search_results_state],
        outputs=[search_results_container, search_results_state]
    )

    # When URL is selected via JS -> Hidden Textbox -> updates state
    url_storage.input(
        fn=lambda x: x,
        inputs=[url_storage],
        outputs=[selected_arxiv_url]
    )
    
    url_storage.change(
        fn=lambda x: x,
        inputs=[url_storage],
        outputs=[selected_arxiv_url]
    )
    
    def on_generate_click(upload, url_from_state, url_from_textbox, deep):
        # Heuristic: If upload is present, use it. Else use URL.
        # This simple logic prefers Upload if both are present.
        # Use url_from_textbox as primary source (persists after refresh), fallback to state
        url = url_from_textbox.strip() if url_from_textbox else (url_from_state or "")
        
        if upload is not None:
            mode = "Upload PDF"
        elif url:
            mode = "arXiv Search"
        else:
            yield "Please select a paper or upload a PDF.", None, None
            return
            
        yield from process_pipeline(mode, upload, url, deep)

    generate_btn.click(
        fn=on_generate_click,
        inputs=[file_upload, selected_arxiv_url, url_storage, use_deep],
        outputs=[status_log, video_player, json_debug_view]
    )
    
    # Setup click handlers for search results using Gradio's js param
    app.load(
        fn=None,
        inputs=None,
        outputs=None,
        js="""
        () => {
            // Use event delegation for dynamically added search results
            if (!window.paperClickHandlerSetup) {
                window.paperClickHandlerSetup = true;
                
                // Add inline copy button to URL field
                function addCopyButton() {
                    const container = document.getElementById('url_storage');
                    console.log('Looking for url_storage:', container);
                    if (container && !container.querySelector('.inline-copy-btn')) {
                        // Try multiple selectors for the input wrapper
                        let wrapper = container.querySelector('.wrap') || container.querySelector('.input-container') || container;
                        let inputEl = container.querySelector('textarea') || container.querySelector('input');
                        console.log('Found wrapper:', wrapper, 'Input:', inputEl);
                        
                        if (inputEl) {
                            // Make sure parent has relative positioning
                            let parent = inputEl.parentElement;
                            parent.style.position = 'relative';
                            
                            const btn = document.createElement('button');
                            btn.className = 'inline-copy-btn';
                            btn.type = 'button';
                            btn.innerHTML = '<span>Copy link</span><svg class="copy-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
                            btn.title = 'Copy URL';
                            
                            // Create tooltip element
                            const tooltip = document.createElement('div');
                            tooltip.className = 'copy-tooltip';
                            tooltip.textContent = 'Link Copied!';
                            btn.appendChild(tooltip);
                            
                            btn.onclick = function(e) {
                                e.preventDefault();
                                e.stopPropagation();
                                if (inputEl && inputEl.value) {
                                    navigator.clipboard.writeText(inputEl.value).then(() => {
                                        tooltip.classList.add('show');
                                        setTimeout(() => { tooltip.classList.remove('show'); }, 2500);
                                    });
                                }
                            };
                            parent.appendChild(btn);
                            console.log('Copy button added!');
                        }
                    }
                }
                
                // Try multiple times with increasing delays
                setTimeout(addCopyButton, 500);
                setTimeout(addCopyButton, 1000);
                setTimeout(addCopyButton, 2000);
                
                // Also use MutationObserver as backup
                const observer = new MutationObserver(function(mutations) {
                    addCopyButton();
                });
                observer.observe(document.body, { childList: true, subtree: true });

                
                document.body.addEventListener('click', function(e) {
                    const item = e.target.closest('.search-result-item');
                    if (!item) return;
                    
                    const url = item.getAttribute('data-url');
                    if (!url) return;
                    
                    console.log("Paper selected:", url);
                    
                    // 1. Deselect all and collapse summaries
                    document.querySelectorAll('.search-result-item').forEach(el => {
                        el.classList.remove('selected');
                        const summary = el.querySelector('.summary-box');
                        if(summary) summary.style.display = 'none';
                    });
                    
                    // 2. Select clicked and expand summary
                    item.classList.add('selected');
                    const summary = item.querySelector('.summary-box');
                    if(summary) summary.style.display = 'block';

                    // 3. Update Gradio hidden textbox
                    const container = document.getElementById('url_storage');
                    if (container) {
                        const input = container.querySelector('textarea') || container.querySelector('input');
                        if (input) {
                            // Set the value using native setter to trigger React/Gradio detection
                            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set 
                                || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                            if (nativeInputValueSetter) {
                                nativeInputValueSetter.call(input, url);
                            } else {
                                input.value = url;
                            }
                            // Dispatch multiple events to ensure Gradio picks it up
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                            input.dispatchEvent(new Event('blur', { bubbles: true }));
                        }
                    }
                });
            }
        }
        """
    )

if __name__ == "__main__":
    app.launch(share=False)
