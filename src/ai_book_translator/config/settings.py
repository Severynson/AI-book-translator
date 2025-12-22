from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    upload_retries: int = 2
    json_repair_retries: int = 2

    translation_chunk_chars: int = 30000
    local_metadata_chunk_chars: int = 8000
    local_metadata_first_chunks_with_title_author_hint: int = 3

    max_chunk_summaries_for_summary_of_summaries: int = 500
