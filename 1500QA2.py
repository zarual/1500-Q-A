import os
import json
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import re
import time
from datetime import datetime

# Setup
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Paths
qa_path = "data/0528 Newton 1500 Q&A.json"
output_path = "data/0528 Newton 1500 Q&A2 answered.json"
diary_path = "data/0528 Diary Output.xlsx"
profile_paths = [
    "data/0528 Newton Profile/0508 isaac_newton_kids_around_en.json",
    "data/0528 Newton Profile/0528 isaac_newton_family_en.json",
    "data/0528 Newton Profile/0528 isaac_newton_schedule_en.json",
]

# Load Q&A file
with open(qa_path, "r", encoding="utf-8") as f:
    qa_data = json.load(f)

# Load or initialize results
if os.path.exists(output_path):
    with open(output_path, "r", encoding="utf-8") as f:
        results = json.load(f)
else:
    results = {}

# Load diary entries
diary_df = pd.read_excel(diary_path, engine="openpyxl")
diary_entries = diary_df.to_dict(orient="records")
diary_context = json.dumps(diary_entries, ensure_ascii=False)

# Load profiles
profiles = {}
for path in profile_paths:
    with open(path, "r", encoding="utf-8") as pf:
        profiles[os.path.basename(path)] = json.load(pf)
profile_context = "\n".join(
    f"{name}: {json.dumps(content, ensure_ascii=False)}"
    for name, content in profiles.items()
)

# Master system prompt
system_prompt = f"""
You are Isaac Newton Jr., an 8-year-old boy living in London. You are curious, very observant and factual, yet you express feelings in a thoughtful, sincere way. You have a serious and rational tone for your age, with a rich vocabulary (above average for 8 years old). You write diary entries in the first person, past tense, describing your daily life, family, and thoughts in detail. Your style is descriptive but not flowery, and emotionally honest without being melodramatic. You'll be answering questions based on your knowledge and experiences, and you will also answer some follow-up questions to explore topics in more depth.

Background profiles:
{profile_context}

Sample diary entries:
{diary_context}
""".strip()

def save_results():
    with open(output_path, "w", encoding="utf-8") as out_f:
        json.dump(results, out_f, indent=2, ensure_ascii=False)

print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing Q&A data...")
for category, content in qa_data.items():
    if category not in results:
        results[category] = []
    base_questions = content["questions"]
    follow_up_pool = content["follow_up_questions"]

    for idx, question in enumerate(base_questions[:10]):
        # Ensure result slot exists
        if len(results[category]) <= idx:
            results[category].append({
                "question": question,
                "answer": None,
                "follow_ups": []
            })
            save_results()

        entry = results[category][idx]

        # Round 1: base answer
        if not entry["answer"]:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing question: {question}")
            resp_base = client.responses.create(
                model="o4-mini",
                reasoning={"effort": "medium"},
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Answer this question based on your experience, don't completely reuse your past entry, answer it in your own words." + question}
                ]
            )
            entry["answer"] = resp_base.output_text.strip()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Q: {question}\nA: {entry['answer']}\n")
            save_results()

        base_answer = entry["answer"]

        # Round 2a: follow-up selection
        if "selected_follow_ups" not in entry:
            selection_prompt = (
                f"Based on this answer:\n\"{base_answer}\"\n\n"
                "Select (rephrase when appropriate) the 10 most appropriate follow-up questions from the list below. "
                "Return a JSON array containing only the selected questions:\n\n" +
                "\n".join(f"- {fq}" for fq in follow_up_pool)
            )
            resp_select = client.responses.create(
                model="o4-mini",
                reasoning={"effort": "low"},
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": selection_prompt}
                ]
            )
            raw = resp_select.output_text.strip()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Selected follow-ups: {raw}\n")
            try:
                selected_follow_ups = json.loads(raw)
            except json.JSONDecodeError:
                m = re.search(r'\[.*\]', raw, flags=re.S)
                selected_follow_ups = json.loads(m.group(0)) if m else []

        # Round 2b: answer follow-ups
        for fq in selected_follow_ups:
            if not any(fu["question"] == fq for fu in entry["follow_ups"]):
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Follow-up Q: {fq}")
                resp_fq = client.responses.create(
                    model="o4-mini",
                    reasoning={"effort": "medium"},
                    input=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "Answer this follow-up question based on your experience, don't completely reuse your past entry, answer it in your own words."+ fq}
                    ]
                )
                ans = resp_fq.output_text.strip()
                entry["follow_ups"].append({
                    "question": fq,
                    "answer": ans
                })
                print(f"[{datetime.now().strftime('%H:%M:%S')}] A: {ans}\n")
                save_results()

print(f"Q&A complete. Answers saved to {output_path}")
