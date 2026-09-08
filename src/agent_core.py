import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

import json
import time
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from google.generativeai.types.content_types import to_part
from sqlalchemy.orm import Session

from src.database import SessionLocal, ConversationModel, AgentExecutionLogModel
from src.schemas import TravelerProfileSchema
from src.llm_client import analyze_and_update_profile_llm, get_prompt_from_db
import src.config as config

# Import tools
from src.tools.search import search_hotels, search_activities, search_transportation, get_sales_lead_status, search_web_for_tourism, search_places, search_knowledge_base
from src.tools.operations import (
    calculate_trip_estimate, create_trip_proposal, submit_sales_lead,
    simulate_trip_change, optimize_trip, create_booking, confirm_booking_payment
)
import google.generativeai as genai


# Tool map for dynamic execution
#بيربط ال String يلي راجع من ال llm بالفنكشن الحقيقي بالبايثون
tool_map = {
    "search_hotels": search_hotels,
    "search_activities": search_activities,
    "search_transportation": search_transportation,
    "calculate_trip_estimate": calculate_trip_estimate,
    "create_trip_proposal": create_trip_proposal,
    "submit_sales_lead": submit_sales_lead,
    "get_sales_lead_status": get_sales_lead_status,
    "simulate_trip_change": simulate_trip_change,
    "optimize_trip": optimize_trip,
    "search_web_for_tourism": search_web_for_tourism,
    "search_places": search_places,
    "search_knowledge_base": search_knowledge_base,
    "create_booking": create_booking,
    "confirm_booking_payment": confirm_booking_payment
}



# Configure Gemini SDK
if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)

def sanitize_value(val: Any) -> Any:
    """
    Recursively converts protobuf types (RepeatedComposite, RepeatedScalarContainer)
    into standard Python lists/dicts so they can be JSON serialized.
    """
    if isinstance(val, (list, tuple)):
        return [sanitize_value(v) for v in val]
    if isinstance(val, dict):
        return {k: sanitize_value(v) for k, v in val.items()}
    # Check for iterable protobuf objects
    if hasattr(val, "__iter__") and not isinstance(val, (str, bytes)):
        try:
            return [sanitize_value(v) for v in val]
        except Exception:
            pass
    return val

def format_traveler_profile(profile: dict) -> str:
    if not profile:
        return "No traveler profile is currently stored."
    
    summary = []
    if profile.get("destination"):
        summary.append(f"- Destination: {profile['destination']}")
    
    adults = profile.get("adults")
    children = profile.get("children")
    if adults is not None:
        summary.append(f"- Adults: {adults}")
    if children is not None:
        summary.append(f"- Children: {children}")
        
    budget = profile.get("budget")
    currency = profile.get("currency")
    if budget is not None:
        summary.append(f"- Budget: {budget} {currency or 'USD'}")
        
    if profile.get("duration_days") is not None:
        summary.append(f"- Duration: {profile['duration_days']} days")
        
    if profile.get("hotel_preference"):
        summary.append(f"- Hotel Preference: {profile['hotel_preference']}")
        
    if profile.get("transportation_preference"):
        summary.append(f"- Transportation Preference: {profile['transportation_preference']}")
        
    interests = profile.get("interests", [])
    if interests:
        summary.append(f"- Interests: {', '.join(interests)}")
        
    reqs = profile.get("special_requests", [])
    if reqs:
        summary.append(f"- Special Requests: {', '.join(reqs)}")
        
    proposal = profile.get("current_proposal")
    if proposal:
        summary.append(f"- Current Saved Proposal: Total cost {proposal.get('total_cost')} USD, including hotel {proposal.get('hotel_name')} and transportation {proposal.get('transportation_type')}.")
        
    return "\n".join(summary)

def send_message_with_retry(
    chat,
    message,
    max_retries=2,
    initial_delay=1
):
    """Sends a message to Gemini chat with retry logic for 429 quota errors."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return chat.send_message(message)
        except Exception as e:
            err_msg = str(e).lower()
            is_rate_limit = any(x in err_msg for x in ["429", "resource_exhausted", "quota", "rate limit", "exhausted"])
            if is_rate_limit and attempt < max_retries - 1:
                print(f"Rate limit (429) hit during chat. Waiting {delay}s before retrying (Attempt {attempt+1}/{max_retries})...")
                time.sleep(delay)
                delay *= 2
                continue
            raise e

def run_tourism_agent(
    conversation_id: str,
    user_message: str,
    model_name: Optional[str] = None
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Orchestrates the Agent Loop.
    Loads history, extracts profile info, runs Gemini function-calling loop,
    logs executions, and saves state to PostgreSQL database.
    
    Returns (final_response_text, execution_steps, metadata).
    """
    start_time = time.time()
    db = SessionLocal()
    
    try:
        if not model_name:
            model_name = config.DEFAULT_MODEL

        # 1. Load or Create Conversation
        conv = db.query(ConversationModel).filter(ConversationModel.id == conversation_id).first()
        if not conv:
            conv = ConversationModel(id=conversation_id, messages=[], traveler_profile={})
            db.add(conv)
            db.commit()
            db.refresh(conv)

        # 2. Extract profile parameters from latest message to update memory
        try:
            current_prof_data = conv.traveler_profile or {}
            # Ensure proper schema defaults
            if not current_prof_data.get("interests"):
                current_prof_data["interests"] = []
            if not current_prof_data.get("accessibility_requirements"):
                current_prof_data["accessibility_requirements"] = []
            if not current_prof_data.get("special_requests"):
                current_prof_data["special_requests"] = []
                
            current_profile_obj = TravelerProfileSchema.model_validate(current_prof_data)
            recent_msgs = conv.messages or []
            
            updated_profile_obj, _ = analyze_and_update_profile_llm(
                user_message=user_message,
                current_profile=current_profile_obj,
                recent_messages=recent_msgs,#بجيب الشاتس كلها عشان لو العميل قرر 4 بدال 5 
                model_name=model_name
            )
            
            conv.traveler_profile = updated_profile_obj.model_dump()#بنحول لجيسن لأنو البوستقري ما بتعرف تتعامل الا مع جيسن
            db.commit()
        except Exception as ee:
            print(f"Skipped profile extraction updates: {ee}")#لو صار انقطاع بالنت او بالاستخراج بنكتب هاي بالتيرمنال بس بوقفش البرنامج 

        profile_summary = format_traveler_profile(conv.traveler_profile)

        # 3. Define System Instruction with Traveler Profile Injection
        prompt_template = get_prompt_from_db(
            "system_instruction",
            default_content="You are an expert Jordan Tourism Sales Qualification Agent. Current Traveler Profile (Memory):\n{profile_summary}"
        )                                    #هون فعليا بمسك يلي جبتهم من الداتا بيس وبعبي البروفايل سمري يلي بالميموري
        system_instruction = prompt_template.format(profile_summary=profile_summary)


        # 4. Prepare History for Gemini Chat
        history = []
        for msg in conv.messages:
            history.append({
                "role": msg["role"],#user or model
                "parts": [msg["content"]]#نص الرسالة
            })

        # 5. Initialize Gemini Chat with Tools
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction,
            tools=list(tool_map.values())
        )
        
        chat = model.start_chat(history=history, enable_automatic_function_calling=False)
        
        # 6. Execute Agent Loop
        iteration = 0
        max_iterations = 7
        steps = []
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        
        # Send user message with retry wrapper
        response = send_message_with_retry(chat, user_message)
        
        # Update tokens if available
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            token_usage["input_tokens"] += response.usage_metadata.prompt_token_count
            token_usage["output_tokens"] += response.usage_metadata.candidates_token_count
            token_usage["total_tokens"] += response.usage_metadata.total_token_count
            
        final_text = ""
        agent_status = "completed"
        
        while iteration < max_iterations:
            # Check for function calls
            function_calls = [part.function_call for part in response.parts if part.function_call]
            
            if not function_calls:
                # No tool calls, we have our final text response
                final_text = response.text
                break
                
            iteration += 1
            function_responses = []
            
            for fn in function_calls:
                tool_name = fn.name
                tool_args = dict(fn.args)
                
                # Check for conversation_id in arguments to automatically inject it
                if "conversation_id" in tool_args and not tool_args["conversation_id"]:
                    tool_args["conversation_id"] = conversation_id
                elif "conversation_id" in tool_args and tool_args["conversation_id"] == "None":
                    tool_args["conversation_id"] = conversation_id
                elif "conversation_id" in tool_args and tool_args["conversation_id"] == "":
                    tool_args["conversation_id"] = conversation_id
                
                print(f"[Agent Loop] Step {iteration}: Calling {tool_name} with args: {tool_args}")
                
                try:
                    tool_fn = tool_map.get(tool_name)
                    if not tool_fn:
                        tool_result = {"success": False, "error": f"Tool '{tool_name}' is not registered."}
                    else:
                        # Special handling if conversation_id is missing but needed
                        if tool_name in ["create_trip_proposal", "submit_sales_lead", "create_booking"]:
                            if not tool_args.get("conversation_id"):
                                tool_args["conversation_id"] = conversation_id
                        
                        raw_result = tool_fn(**tool_args)
                        tool_result = json.loads(raw_result)
                        
                    steps.append({
                        "step_num": len(steps) + 1,
                        "tool_name": tool_name,
                        "tool_args": sanitize_value(tool_args),
                        "tool_result": sanitize_value(tool_result),
                        "status": "success" if tool_result.get("success") else "failed"
                    })
                except Exception as e:
                    tool_result = {"success": False, "error": f"Internal execution error: {str(e)}"}
                    steps.append({
                        "step_num": len(steps) + 1,
                        "tool_name": tool_name,
                        "tool_args": sanitize_value(tool_args),
                        "tool_result": sanitize_value(tool_result),
                        "status": "error"
                    })
                
                # Construct function response Part using to_part helper
                function_responses.append(
                    to_part({
                        "function_response": {
                            "name": tool_name,
                            "response": tool_result
                        }
                    })
                )
            
            # Send results back to LLM with retry wrapper
            response = send_message_with_retry(chat, function_responses)
            
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                token_usage["input_tokens"] += response.usage_metadata.prompt_token_count
                token_usage["output_tokens"] += response.usage_metadata.candidates_token_count
                token_usage["total_tokens"] += response.usage_metadata.total_token_count
                
        # If we reached maximum iterations without completing
        if iteration >= max_iterations and not final_text:#(هاي عشان اذا الايجنت لف 7 مرات كاملين وما اعطى جواب نهائي للعميل بكون علق ف بوقف)
            agent_status = "max_iterations_reached"
            final_text = "I went into a long search loop. Let's refine your trip details so I can assist you better!"
            
        # 7. Update conversation history
        updated_messages = conv.messages or []
        updated_messages.append({"role": "user", "content": user_message})
        updated_messages.append({"role": "model", "content": final_text})
        conv.messages = updated_messages
        db.commit()
        
        latency = time.time() - start_time
        
        # Calculate cost based on model
        cost_rate_in = 0.075 / 1_000_000 if "pro" not in model_name.lower() else 1.25 / 1_000_000
        cost_rate_out = 0.30 / 1_000_000 if "pro" not in model_name.lower() else 5.00 / 1_000_000
        cost = (token_usage["input_tokens"] * cost_rate_in) + (token_usage["output_tokens"] * cost_rate_out)
        
        metadata = {
            "model": model_name,
            "latency_seconds": latency,
            "token_usage": token_usage,
            "estimated_cost_usd": cost,
            "iterations": iteration,
            "status": agent_status
        }
        
        # 8. Log Execution
        execution_log = AgentExecutionLogModel(
            conversation_id=conversation_id,
            user_request=user_message,
            iterations=iteration,
            steps=steps,
            latency_seconds=latency,
            token_usage=token_usage,
            estimated_cost_usd=cost,
            status=agent_status
        )
        db.add(execution_log)
        db.commit()
        
        return final_text, steps, metadata
        
    except Exception as e:
        db.rollback()#الغيلي كمان كل التعديلات المؤقتى يلي عملناها بهاي المحاولة
        print(f"Error running agent loop: {e}")
        # Fallback response
        err_msg = "Sorry, I encountered a technical issue while processing your request. Please try again."
        return err_msg, [], {"status": "error", "error": str(e), "latency_seconds": time.time() - start_time}
    finally:
        db.close()
