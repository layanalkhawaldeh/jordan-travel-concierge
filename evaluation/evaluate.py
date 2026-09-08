import os
import sys
import json
import time
from typing import Dict, Any, List

# Ensure the root directory is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.llm_client import analyze_inquiry_llm
from src.business_logic import qualify_lead
from src.schemas import LeadQualification

# Price estimation helper
def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    if "pro" in model.lower():
        input_rate = 1.25 / 1_000_000
        output_rate = 5.00 / 1_000_000
    else:  # Flash
        input_rate = 0.075 / 1_000_000
        output_rate = 0.30 / 1_000_000
    return (input_tokens * input_rate) + (output_tokens * output_rate)

def compare_strings(s1: Any, s2: Any) -> bool:
    if s1 is None and s2 is None:
        return True
    if s1 is None or s2 is None:
        return False
    return str(s1).strip().lower() == str(s2).strip().lower() #لو الـ AI استخرج اسم البلد وحرفها كابتل "Jordan"،
    # والحقيقة المكتوبة بالملف هي "jordan" (حرف صغير)، ما يعتبرها غلط

def run_evaluation(prompt_version: str, dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
    print(f"\n--- Running Evaluation for Prompt {prompt_version.upper()} ---")
    results = []
    
    total_latency = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    
    # Metrics counters
    valid_json_count = 0
    tourism_related_correct = 0
    destination_correct = 0
    travelers_correct = 0
    duration_correct = 0
    budget_amount_correct = 0
    budget_currency_correct = 0
    lead_qual_correct = 0
    hallucination_count = 0

    for idx, case in enumerate(dataset):#هاد بخلينا نلف عال 30 حالة وحدة وحدة  , وبيعطينا شغلتين مع بعض , ال index وال case
        print(f"[{idx+1}/{len(dataset)}] Evaluating case: {case['description']}...")
        message = case["message"]
        gt = case["ground_truth"]

        # Call LLM
        try:
            inquiry_data, meta = analyze_inquiry_llm(message, prompt_version=prompt_version)
            # Qualify lead deterministically
            lead_qual = qualify_lead(inquiry_data)
            valid_json = True
        except Exception as e:#هون ازا صار كراش بسجل انو الحالة فشلت وبكمل للي بعدها
            print(f"Error evaluating case {case['id']}: {e}")
            valid_json = False
            results.append({
                "id": case["id"],
                "error": str(e),
                "success": False
            })
            continue

        # Update metadata stats
        total_latency += meta["latency_seconds"]
        total_input_tokens += meta["input_tokens"]
        total_output_tokens += meta["output_tokens"]
        if valid_json:
            valid_json_count += 1

        # Evaluate correctness
        is_tourism_ok = inquiry_data.is_tourism_related == gt["is_tourism_related"]
        if is_tourism_ok:
            tourism_related_correct += 1

        # For tourism inquiries, evaluate details
        dest_ok = True
        travelers_ok = True
        duration_ok = True
        budget_amt_ok = True
        budget_curr_ok = True
        lead_qual_ok = True
        
        if gt["is_tourism_related"]:
            dest_ok = compare_strings(inquiry_data.destination_country, gt["destination_country"])
            if dest_ok:
                destination_correct += 1

            travelers_ok = (inquiry_data.travelers.adults == gt["adults"]) and (inquiry_data.travelers.children == gt["children"])
            if travelers_ok:
                travelers_correct += 1

            duration_ok = inquiry_data.duration_days == gt["duration_days"]
            if duration_ok:
                duration_correct += 1

            budget_amt_ok = inquiry_data.budget.amount == gt["budget_amount"]
            if budget_amt_ok:
                budget_amount_correct += 1

            budget_curr_ok = compare_strings(inquiry_data.budget.currency, gt["budget_currency"])
            if budget_curr_ok:
                budget_currency_correct += 1

            lead_qual_ok = lead_qual.value == gt["lead_qualification"]
            if lead_qual_ok:
                lead_qual_correct += 1

           #ازا الحقيقة بتحطي انو البلد بالمسج None بس ال AI كتب اسم بلد , هاد معناه انو ألف ف بنزيد عداد الهلوسات
            if gt["destination_country"] is None and inquiry_data.destination_country is not None:
                hallucination_count += 1
                
            if gt["duration_days"] is None and inquiry_data.duration_days is not None:
                hallucination_count += 1
            if gt["budget_amount"] is None and inquiry_data.budget.amount is not None:
                hallucination_count += 1
            if gt["adults"] is None and inquiry_data.travelers.adults is not None:
                hallucination_count += 1
        else:
            #ازا كانت الرسالة مش سياحية بنهتم نفحص هل الكود صنف الزبون صح انو اوت اوف سكوب ؟
            lead_qual_ok = lead_qual.value == gt["lead_qualification"]
            if lead_qual_ok:
                lead_qual_correct += 1

#لكل حالة من ال 30 بكتب تقرير تفصيلي
        results.append({
            "id": case["id"],
            "description": case["description"],
            "success": True,
            "latency": meta["latency_seconds"],
            "tokens": {
                "input": meta["input_tokens"],
                "output": meta["output_tokens"],
                "total": meta["total_tokens"]
            },
            "ground_truth": gt,
            "extracted": {
                "is_tourism_related": inquiry_data.is_tourism_related,
                "destination_country": inquiry_data.destination_country,
                "travelers": inquiry_data.travelers.model_dump(),
                "duration_days": inquiry_data.duration_days,
                "budget": inquiry_data.budget.model_dump(),
                "lead_qualification": lead_qual.value
            },
            "correctness": {
                "is_tourism_related": is_tourism_ok,
                "destination_country": dest_ok,
                "travelers": travelers_ok,
                "duration_days": duration_ok,
                "budget_amount": budget_amt_ok,
                "budget_currency": budget_curr_ok,
                "lead_qualification": lead_qual_ok
            }
        })
        
        # Add a tiny sleep to avoid rate limiting
        time.sleep(0.5)

    n_cases = len(dataset)
    tourism_cases = [c for c in dataset if c["ground_truth"]["is_tourism_related"]]
    n_tourism = len(tourism_cases)#عدد الحالات يلي هي سياحية فعلا بالملف

    #اشياء التواريخ والبلد والميزانية بقسمها ع n_tourism لانو هي يلي فيها اسماء عنجد
    summary = {
        "prompt_version": prompt_version,
        "valid_json_rate": (valid_json_count / n_cases) * 100,
        "tourism_related_accuracy": (tourism_related_correct / n_cases) * 100,
        "destination_accuracy": (destination_correct / n_tourism) * 100,
        "travelers_accuracy": (travelers_correct / n_tourism) * 100,
        "duration_accuracy": (duration_correct / n_tourism) * 100,
        "budget_amount_accuracy": (budget_amount_correct / n_tourism) * 100,
        "budget_currency_accuracy": (budget_currency_correct / n_tourism) * 100,
        "lead_qualification_accuracy": (lead_qual_correct / n_cases) * 100,
        "total_hallucinations": hallucination_count,
        "average_latency_seconds": total_latency / n_cases,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost_usd": estimate_cost(total_input_tokens, total_output_tokens, "gemini-3.6-flash")
    }
    
    return {"summary": summary, "details": results}

def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(current_dir, "dataset.json")
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    print(f"Loaded {len(dataset)} evaluation cases.")

    # Evaluate Prompt V1
    v1_results = run_evaluation("v1", dataset)
    
    # Evaluate Prompt V2
    v2_results = run_evaluation("v2", dataset)

    # Save results
    output_path = os.path.join(current_dir, "evaluation_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "v1": v1_results,
            "v2": v2_results
        }, f, indent=2, ensure_ascii=False)
        
    print(f"\nDetailed evaluation results saved to: {output_path}")

    # Print summary table
    v1_sum = v1_results["summary"]
    v2_sum = v2_results["summary"]
    
    print("\n" + "="*60)
    print("                 EVALUATION SUMMARY COMPARISON")
    print("="*60)
    print(f"{'Metric':<32} | {'Prompt V1':<12} | {'Prompt V2':<12}")
    print("-"*60)
    print(f"{'Valid Structured Output Rate':<32} | {v1_sum['valid_json_rate']:.1f}%       | {v2_sum['valid_json_rate']:.1f}%")
    print(f"{'Tourism Scope Accuracy':<32} | {v1_sum['tourism_related_accuracy']:.1f}%       | {v2_sum['tourism_related_accuracy']:.1f}%")
    print(f"{'Destination Country Accuracy':<32} | {v1_sum['destination_accuracy']:.1f}%       | {v2_sum['destination_accuracy']:.1f}%")
    print(f"{'Travelers Count Accuracy':<32} | {v1_sum['travelers_accuracy']:.1f}%       | {v2_sum['travelers_accuracy']:.1f}%")
    print(f"{'Trip Duration Accuracy':<32} | {v1_sum['duration_accuracy']:.1f}%       | {v2_sum['duration_accuracy']:.1f}%")
    print(f"{'Budget Amount Accuracy':<32} | {v1_sum['budget_amount_accuracy']:.1f}%       | {v2_sum['budget_amount_accuracy']:.1f}%")
    print(f"{'Budget Currency Accuracy':<32} | {v1_sum['budget_currency_accuracy']:.1f}%       | {v2_sum['budget_currency_accuracy']:.1f}%")
    print(f"{'Lead Qualification Accuracy':<32} | {v1_sum['lead_qualification_accuracy']:.1f}%       | {v2_sum['lead_qualification_accuracy']:.1f}%")
    print("-"*60)
    print(f"{'Total Hallucination Incidents':<32} | {v1_sum['total_hallucinations']:<12} | {v2_sum['total_hallucinations']:<12}")
    print(f"{'Average Latency (seconds)':<32} | {v1_sum['average_latency_seconds']:.2f}s       | {v2_sum['average_latency_seconds']:.2f}s")
    print(f"{'Total Input / Output Tokens':<32} | {v1_sum['total_input_tokens']}/{v1_sum['total_output_tokens']}  | {v2_sum['total_input_tokens']}/{v2_sum['total_output_tokens']}")
    print(f"{'Estimated Cost (30 runs)':<32} | ${v1_sum['total_cost_usd']:.5f}    | ${v2_sum['total_cost_usd']:.5f}")
    print("="*60)

if __name__ == "__main__":
    main()
