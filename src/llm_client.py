import os
import time
import json
import google.generativeai as genai
from typing import Dict, Any, Tuple, Optional, List
import sys

# Ensure src path resolved
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from schemas import TravelerProfileSchema
import config
from src.database import SessionLocal, PromptModel

# Configure Gemini SDK
if config.GEMINI_API_KEY and config.GEMINI_API_KEY.lower() != "mock":
    genai.configure(api_key=config.GEMINI_API_KEY)

def get_prompt_from_db(prompt_id: str, default_content: str) -> str:
    """Retrieves prompt template from PostgreSQL database prompts table."""
    db = SessionLocal()
    try:
        prompt = db.query(PromptModel).filter(PromptModel.id == prompt_id).first()
        if prompt:
            return prompt.prompt_data
    except Exception as e:
        print(f"Warning: Could not load prompt {prompt_id} from database: {e}")
    finally:
        db.close()
    return default_content

def _generate_content_with_retry(model,prompt,generation_config,max_retries=2,initial_delay=1):
    """Calls model.generate_content with exponential backoff on 429 ResourceExhausted errors."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt, generation_config=generation_config)
        except Exception as e:
            err_msg = str(e).lower()
            is_rate_limit = any(x in err_msg for x in ["429", "resource_exhausted", "quota", "rate limit", "exhausted"])
            if is_rate_limit and attempt < max_retries - 1:
                print(f"Rate limit (429) hit. Waiting {delay}s before retrying (Attempt {attempt+1}/{max_retries})...")
                time.sleep(delay)
                delay *= 2
                continue
            raise e

def format_chat_history(messages: List[Dict[str, str]]) -> str:
    """Formats raw database messages list into a clean string for prompt context."""
    formatted = []
    for msg in messages:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        formatted.append(f"{role_label}: {msg['content']}")
    return "\n".join(formatted) if formatted else "No previous messages."

def analyze_and_update_profile_llm(
    user_message: str,
    current_profile: TravelerProfileSchema,
    recent_messages: List[Dict[str, str]],
    model_name: Optional[str] = None
) -> Tuple[TravelerProfileSchema, Dict[str, Any]]:
    """
    Calls LLM to extract new info from user message and update traveler profile.
    Returns (updated_profile, metadata).
    """
    if not model_name:
        model_name = config.DEFAULT_MODEL

    model = genai.GenerativeModel(model_name)
    prompt_template = get_prompt_from_db(
        "profile_extraction", 
        default_content="You are an AI assistant. Extract traveler profile details from the user message: {user_message}. Current profile: {current_profile}. History: {chat_history}"
    )
    
    chat_history_str = format_chat_history(recent_messages)
    
    prompt = prompt_template.format(
        current_profile=json.dumps(current_profile.model_dump(), indent=2, ensure_ascii=False),
        chat_history=chat_history_str,
        customer_message=user_message # Handles extraction_prompt_v2 format
    )

    start_time = time.time()
    try:
       response = _generate_content_with_retry(
       model,
       prompt + "\nReturn ONLY valid JSON matching the requested traveler profile fields.",
    generation_config=genai.GenerationConfig(
        response_mime_type="application/json",#هون انا بجبر جيميناي يلتزم بجيسن
        temperature=0.0
    )

        )
    except Exception as e:
        err_msg = str(e).lower()
        if "429" in err_msg or "resource_exhausted" in err_msg:
            raise e
        
        # Fallback to plain JSON generation if schema parsing fails
        print(f"Structured schema failed, falling back to plain JSON prompt: {e}")
        response = _generate_content_with_retry(
            model,
            prompt + "\nIMPORTANT: You must return a valid JSON object matching the requested schema.",
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
        )

    latency = time.time() - start_time

    # Handle usage metadata
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage["input_tokens"] = response.usage_metadata.prompt_token_count
        usage["output_tokens"] = response.usage_metadata.candidates_token_count
        usage["total_tokens"] = response.usage_metadata.total_token_count

    metadata = {
        "model": model_name,
        "latency_seconds": latency,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "total_tokens": usage["total_tokens"],
        "is_mock": False
    }

    # Validate schema
    try:
        raw_text = response.text.strip()
        updated_profile = TravelerProfileSchema.model_validate_json(raw_text)
    except Exception as parse_error:
        print(f"Validation failed for extraction response: {response.text}\nError: {parse_error}")
        updated_profile = current_profile  # Keep previous state if parsing completely fails

    return updated_profile, metadata

def generate_chatbot_response_llm(
    user_message: str,
    current_profile: TravelerProfileSchema,
    lead_status: str,#hot / incomlete or cold
    missing_fields: List[str],
    recent_messages: List[Dict[str, str]],
    model_name: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Calls LLM to generate the next chatbot conversational turn/question.
    Returns (assistant_reply, metadata).
    """
    if not model_name:
        model_name = config.DEFAULT_MODEL

    # Live Mode (Mocks removed)
    model = genai.GenerativeModel(model_name)
    
    # Load prompt from database
    prompt_template = get_prompt_from_db(
        "response_generation",
        default_content="You are a premier tourism agent. Reply politely. Profile: {current_profile}. Status: {lead_status}. Message: {user_message}"
    )
    
    chat_history_str = format_chat_history(recent_messages)
    
    # Render prompt
    prompt = prompt_template.format(
        current_profile=json.dumps(current_profile.model_dump(), indent=2, ensure_ascii=False),
        lead_status=lead_status,
        missing_fields=", ".join(missing_fields) if missing_fields else "None",
        chat_history=chat_history_str,
        user_message=user_message,
        original_message=user_message, # support default response_prompt_v1 keys
        inquiry_summary=json.dumps(current_profile.model_dump(), indent=2, ensure_ascii=False),
        lead_qualification=lead_status,
        recommended_next_action="Ask for missing information",
        missing_info_list=", ".join(missing_fields) if missing_fields else "None"
    )

    start_time = time.time()
    response = _generate_content_with_retry(
        model, prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.7
        )
    )
    latency = time.time() - start_time

    # Handle usage metadata
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage["input_tokens"] = response.usage_metadata.prompt_token_count
        usage["output_tokens"] = response.usage_metadata.candidates_token_count
        usage["total_tokens"] = response.usage_metadata.total_token_count

    metadata = {
        "model": model_name,
        "latency_seconds": latency,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "total_tokens": usage["total_tokens"],
        "is_mock": False
    }

    return response.text.strip(), metadata
