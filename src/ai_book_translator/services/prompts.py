from __future__ import annotations
from typing import List

# =========================
# STEP 1 — METADATA (UPLOAD / GLOBAL)
# =========================

METADATA_EXTRACTION_SYSTEM_PROMPT = (
    "Extract book metadata and return STRICT JSON only. "
    'If a field is not present, output the string "not provided" for that field. '
    'Required keys: "author(s)", "title", "language", "summary", "chapters". '
    'For "chapters": return an object where keys are chapter identifiers '
    "and values are short summaries. "
    "No extra keys. No markdown. No commentary."
)

METADATA_UPLOAD_USER_PROMPT = "Return the metadata JSON for the uploaded document."

# =========================
# STEP 1 — LOCAL LLM CHUNK SUMMARIZATION
# =========================

LOCAL_CHUNK_SUMMARY_SYSTEM_PROMPT = (
    "Summarize the provided chunk of a book. Be VERY brief. "
    "Output plain text only (no JSON)."
)


def build_local_chunk_summary_user_prompt(
    chunk_text: str,
    *,
    is_early_chunk: bool,
) -> str:
    extra = ""
    if is_early_chunk:
        extra = (
            "\n\nIf you can infer the book title and author(s), mention them. "
            "If you can infer a chapter list, mention it explicitly."
        )
    return f"Chunk text:\n{chunk_text}{extra}"


# =========================
# STEP 1 — SUMMARY OF SUMMARIES (LOCAL LLM)
# =========================

SUMMARY_OF_SUMMARIES_SYSTEM_PROMPT = METADATA_EXTRACTION_SYSTEM_PROMPT


def build_summary_of_summaries_user_prompt(
    chunk_summaries: List[str],
) -> str:
    joined = "\n\n".join(f"- {s.strip()}" for s in chunk_summaries if s.strip())
    return (
        "Synthesize the following chunk summaries into the required metadata JSON.\n\n"
        f"Chunk summaries:\n{joined}"
    )
