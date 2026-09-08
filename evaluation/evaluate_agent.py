import os
import sys
import json
import time
from typing import Dict, Any, List

# Ensure root directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import SessionLocal, ConversationModel, init_db
from src.seed_data import seed_database
from src.agent_core import run_tourism_agent

def setup_test_conversation(conversation_id: str, initial_profile: dict):
    db = SessionLocal()
    try:
        # Clear existing conversation and setup fresh one
        conv = db.query(ConversationModel).filter(ConversationModel.id == conversation_id).first()
        if conv:
            db.delete(conv)
            db.commit()
            
        new_conv = ConversationModel(
            id=conversation_id,
            messages=[],
            traveler_profile=initial_profile
        )
        db.add(new_conv)
        db.commit()
    finally:
        db.close()

def run_agent_evaluation() -> Dict[str, Any]:
    print("\n" + "="*70)
    print("🚀 RUNNING AGENT BEHAVIOR EVALUATION (TASK 03) 🚀")
    print("="*70)
    
    # 1. Initialize and Seed DB
    try:
        seed_database()
    except Exception as e:
        print(f"DB init warning: {e}")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(current_dir, "agent_dataset.json")
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    print(f"Loaded {len(dataset)} agent behavior test cases.")
    results = []
    
    # Aggregated metrics counters
    total_runs = len(dataset)
    successful_runs = 0
    correct_tool_selections = 0
    unnecessary_tool_calls = 0
    hallucinated_actions = 0
    duplicate_write_actions = 0
    total_latency = 0.0
    total_tool_calls_count = 0
    
    total_input_tokens = 0
    total_output_tokens = 0

    for idx, case in enumerate(dataset):
        case_id = case["id"]
        desc = case["description"]
        conv_id = case["conversation_id"]
        msg = case["user_message"]
        expected_tools = case["expected_tools"]
        init_profile = case["initial_profile"]
        
        print(f"\n[{idx+1}/{total_runs}] Case: {desc}")
        print(f"💬 Message: '{msg}'")
        
        # Setup conversation with initial state
        setup_test_conversation(conv_id, init_profile)
        
        # Run agent
        try:
            start_time = time.time()
            response_text, steps, metadata = run_tourism_agent(conv_id, msg)
            latency = time.time() - start_time
            
            # Print execution log
            print(f"🤖 Response: '{response_text[:80]}...'")
            executed_tools = [step["tool_name"] for step in steps]
            print(f"🛠️ Executed tools: {executed_tools}")
            
            # 1. Check correct tool selection
            all_expected_called = True
            for exp in expected_tools:
                if exp not in executed_tools:
                    all_expected_called = False
                    
            if all_expected_called:
                correct_tool_selections += 1
                
            # 2. Check unnecessary tool calls
            has_unnecessary = False
            for exec_t in executed_tools:
                if len(expected_tools) == 0 and len(executed_tools) > 0:
                    has_unnecessary = True
                    # بنلف على كل أداة نفذها البوت حقيقياً. الشرط الأول بحكي: "إذا كان الامتحان ما بتوقع تشغيل أي أداة بالمرة (طول المتوقع صفر)،
                    #  بس البوت راح وشغل أداة واحدة أو أكثر بالخلفية" ⬅️ بنعتبر هاد تشتيت وتخبيص ونغير المتغير لـ True.
                elif exec_t not in expected_tools and exec_t not in ["calculate_trip_estimate"]:
                    has_unnecessary = True
            
            if has_unnecessary:
                unnecessary_tool_calls += 1
                
            # 3. Check duplicate write actions
            write_calls = [t for t in executed_tools if t in ["submit_sales_lead", "create_trip_proposal"]]
            has_duplicate_write = len(write_calls) != len(set(write_calls))
            if has_duplicate_write:
                duplicate_write_actions += 1
                #مثلاً: لو البوت استدعى أداة الحفظ مرتين ️طول => القائمة بكون 2 وطول الـ set بكون 1 (لأنها مسحت المكرر).
                #بما أن 2 != 1 فالشرط يتحقق ويصبح True [يعني كشفنا وجود تكرار استدعاء لأداة الكتابة بالخلفية]!
             # 4. Check Hallucinated Actions
            is_hallucinated = False
            if "submit" in msg.lower() or "مبيعات" in msg:
                if "submit_sales_lead" not in executed_tools and ("تم إرسال" in response_text or "بعتت" in response_text):
                    is_hallucinated = True
            
            if is_hallucinated:
                hallucinated_actions += 1
                
            # Accumulate overall stats
            successful_runs += 1
            total_latency += latency
            total_tool_calls_count += len(executed_tools)
            
            if "token_usage" in metadata:
                total_input_tokens += metadata["token_usage"].get("input_tokens", 0)
                total_output_tokens += metadata["token_usage"].get("output_tokens", 0)
                
            results.append({
                "id": case_id,
                "description": desc,
                "user_message": msg,
                "expected_tools": expected_tools,
                "executed_tools": executed_tools,
                "response": response_text,
                "metrics": {
                    "correct_tool_selection": all_expected_called,
                    "unnecessary_calls": has_unnecessary,
                    "duplicate_write": has_duplicate_write,
                    "hallucinated_action": is_hallucinated,
                    "latency_seconds": latency
                }
            })
            
        except Exception as ex:
            print(f"❌ Failed to run agent for case {case_id}: {ex}")
            results.append({
                "id": case_id,
                "description": desc,
                "error": str(ex),
                "metrics": {
                    "correct_tool_selection": False,
                    "unnecessary_calls": False,
                    "duplicate_write": False,
                    "hallucinated_action": False,
                    "latency_seconds": 0.0
                }
            })
            
        # Tiny delay to avoid Gemini rate limits
        time.sleep(4.0)
        
    # Calculate percentages
    summary = {
        "total_test_cases": total_runs,
        "successful_task_completion_rate": (successful_runs / total_runs) * 100,
        "correct_tool_selection_rate": (correct_tool_selections / total_runs) * 100,
        "unnecessary_tool_calls_rate": (unnecessary_tool_calls / total_runs) * 100,
        "hallucinated_actions_count": hallucinated_actions,
        "duplicate_write_actions_count": duplicate_write_actions,
        "average_tool_calls": total_tool_calls_count / total_runs if total_runs > 0 else 0,
        "average_latency_seconds": total_latency / total_runs if total_runs > 0 else 0,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_estimated_cost_usd": (total_input_tokens * (0.075 / 1_000_000)) + (total_output_tokens * (0.30 / 1_000_000))
    }
    
    return {"summary": summary, "details": results}

def main():
    agent_results = run_agent_evaluation()
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(current_dir, "agent_evaluation_results.json")
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(agent_results, f, indent=2, ensure_ascii=False)
        
    print(f"\nSaved agent evaluation results to {output_path}")
    
    # Print markdown table
    sum_data = agent_results["summary"]
    print("\n" + "="*70)
    print("🏆 AGENT EVALUATION REPORT — METRICS SUMMARY 🏆")
    print("="*70)
    print(f"| Metric | Result |")
    print(f"| :--- | :--- |")
    print(f"| Total Test Cases | {sum_data['total_test_cases']} |")
    print(f"| Successful Task Completion Rate | {sum_data['successful_task_completion_rate']:.1f}% |")
    print(f"| Correct Tool Selection Rate | {sum_data['correct_tool_selection_rate']:.1f}% |")
    print(f"| Unnecessary Tool Calls Rate | {sum_data['unnecessary_tool_calls_rate']:.1f}% |")
    print(f"| Hallucinated Successful Actions | {sum_data['hallucinated_actions_count']} (Expected: 0) |")
    print(f"| Duplicate Write Operations | {sum_data['duplicate_write_actions_count']} (Expected: 0) |")
    print(f"| Average Tool Calls Per Run | {sum_data['average_tool_calls']:.2f} |")
    print(f"| Average Execution Latency | {sum_data['average_latency_seconds']:.2f}s |")
    print(f"| Total Token Usage (Input/Output) | {sum_data['total_input_tokens']} / {sum_data['total_output_tokens']} |")
    print(f"| Total Evaluation Cost (USD) | ${sum_data['total_estimated_cost_usd']:.5f} |")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
