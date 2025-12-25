from ai_book_translator.services.prompts import build_translation_user_prompt

def test_chapter_formatting():
    context = {
        "title": "Test Book",
        "author(s)": "Test Author",
        "summary": "Test Summary",
        "chapters": {
            "Chapter 1": {"general": "Short summary 1", "detailed": "Detailed summary 1"},
            "Chapter 2": {"general": "Short summary 2", "detailed": "Detailed summary 2"},
            "Chapter 3": {"general": "Short summary 3", "detailed": "Detailed summary 3"},
        }
    }
    
    # Test 1: Current chapter is "Chapter 2"
    prompt = build_translation_user_prompt(
        chunk_text="Some text",
        target_language="Ukrainian",
        current_chapter="Chapter 2",
        context=context
    )
    
    print(prompt)
    
    # Expectation: 
    # - Chapter 1 - Short summary 1
    # - Chapter 2 - Detailed summary 2
    # - Chapter 3 - Short summary 3
    
    assert "- Chapter 1 - Short summary 1" in prompt
    assert "- Chapter 2 - Detailed summary 2" in prompt
    assert "- Chapter 3 - Short summary 3" in prompt
    
    # Ensure "Detailed summary 1" is NOT in prompt
    assert "Detailed summary 1" not in prompt

def test_chapter_formatting_no_current_chapter():
    context = {
        "chapters": {
            "Chapter 1": {"general": "Short summary 1", "detailed": "Detailed summary 1"},
        }
    }
    
    prompt = build_translation_user_prompt(
        chunk_text="Some text",
        target_language="Ukrainian",
        current_chapter=None,
        context=context
    )
    
    # Expectation:
    # - Chapter 1 - Short summary 1 (since current is None, none match)
    
    assert "- Chapter 1 - Short summary 1" in prompt
    assert "Detailed summary 1" not in prompt

def test_chapter_formatting_numeric_string_mismatch():
    context = {
        "chapters": {
            "Chapter 1": {"general": "Short summary 1", "detailed": "Detailed summary 1"},
        }
    }
    
    # If current_chapter is "1" but key is "Chapter 1", exact match fails, so it uses general.
    # This is current expected behavior unless I implemented fuzzy matching (which I didn't).
    prompt = build_translation_user_prompt(
        chunk_text="Some text",
        target_language="Ukrainian",
        current_chapter="1",
        context=context
    )
    
    assert "- Chapter 1 - Short summary 1" in prompt
