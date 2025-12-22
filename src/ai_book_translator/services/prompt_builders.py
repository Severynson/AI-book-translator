from __future__ import annotations
from typing import List

def build_step1_metadata_prompt() -> str:
    return (
        "Extract book metadata and return STRICT JSON only. "
        "If a field is not present, output the string \"not provided\" for that field. "
        "Required keys: \"author(s)\", \"title\", \"language\", \"summary\", \"chapters\". "
        "For \"chapters\": return an object where keys are chapter identifiers and values are short summaries. "
        "No extra keys. No markdown. No commentary."
    )

def build_step1_user_prompt_upload() -> str:
    return "Return the metadata JSON for the uploaded document."

def build_local_chunk_summary_system_prompt() -> str:
    return (
        "Summarize the provided chunk of a book. Be VERY brief. "
        "Output plain text only (no JSON)."
    )

def build_local_chunk_summary_user_prompt(chunk_text: str, is_early_chunk: bool) -> str:
    extra = ""
    if is_early_chunk:
        extra = (
            "\n\nIf you can infer the book title and author(s), mention them. "
            "If you can infer a chapter list, mention it explicitly."
        )
    return f"Chunk text:\n{chunk_text}{extra}"

def build_step1_summary_of_summaries_system_prompt() -> str:
    return build_step1_metadata_prompt()

def build_step1_summary_of_summaries_user_prompt(chunk_summaries: List[str]) -> str:
    joined = "\n\n".join(f"- {s.strip()}" for s in chunk_summaries if s.strip())
    return (
        "Synthesize the following chunk summaries into the required metadata JSON.\n\n"
        f"Chunk summaries:\n{joined}"
    )
