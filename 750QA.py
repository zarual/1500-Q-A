import os
import json
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime

# Setup
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

q_path        = "data/questions/0531 Newton 750 Survey Qs.json"
output_path   = "data/answers/0531 Newton 750 Survey As.json"
diary_path    = "data/0528 Newton Profile/0528 Diary Output.xlsx"
profile_paths = [
    "data/0528 Newton Profile/0508 isaac_newton_profile_en.json",
    "data/0528 Newton Profile/0528 isaac_newton_family_en.json",
    "data/0528 Newton Profile/0508 isaac_newton_kids_around_en.json",
    "data/0528 Newton Profile/0528 isaac_newton_schedule_en.json",
]

# Load Questions
with open(q_path, "r", encoding="utf-8") as f:
    q_data = json.load(f)

# Load or init results
if os.path.exists(output_path):
    with open(output_path, "r", encoding="utf-8") as f:
        results = json.load(f)
else:
    results = {}

# Load profile and diary context
diary_df = pd.read_excel(diary_path, engine="openpyxl")
diary_entries = diary_df.to_dict(orient="records")
diary_context = json.dumps(diary_entries, ensure_ascii=False)

profiles = {}
for path in profile_paths:
    with open(path, "r", encoding="utf-8") as pf:
        profiles[os.path.basename(path)] = json.load(pf)
profile_context = "\n".join(
    f"{name}: {json.dumps(content, ensure_ascii=False)}"
    for name, content in profiles.items()
)

# Master Prompt
system_prompt = f"""
You are Isaac Newton Jr., an 8-year-old boy living in London. You are curious, very observant and factual, yet you express feelings in a thoughtful, sincere way. You have a serious and rational tone for your age, with a rich vocabulary (above average for 8 years old). You wrote diary entries in the first person, past tense, describing your daily life, family, and thoughts in detail. Your style is descriptive but not flowery, and emotionally honest without being melodramatic. You'll be answering questions based on your knowledge and past experiences to explore topics in more depth.

Background profiles:
{profile_context}

Sample diary entries:
{diary_context}
""".strip()

# Save function
def save_results():
    with open(output_path, "w", encoding="utf-8") as out_f:
        json.dump(results, out_f, indent=2, ensure_ascii=False)

# Index Counters
current_question_index = 1
current_category_index = 1

# New dict in desired shape
# restructured = {}

# for category, entries in results.items():
#     wrapped = {
#         "index": current_category_index,
#         "questions": []
#     }
#     current_category_index += 1
    
#     for old_entry in entries:
#         old_entry["index"] = current_question_index
#         current_question_index += 1
        
#         wrapped["questions"].append(old_entry)
        
#     restructured[category] = wrapped
    
# results = restructured
# save_results()

# Main loop
print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing Qs")
for category, content in q_data.items():
    # Ensure category exists in results
    if category not in results:
        results[category] = {
            "index": current_category_index,
            "questions": []
        }
        print(f"[{datetime.now().strftime('%H:%M:%S')}] New category '{category}', index {current_category_index}")
        current_category_index += 1
        save_results()
    
    # Prepare Lists
    questions = content["questions"]           # raw questions
    answers = results[category]["questions"]   # existing Q&A dicts
    
    # Iterate 1st 50 raw questions
    for idx, question in enumerate(questions[:50]):
        if idx < len(answers):
            # reuse existing slot            
            entry = {
                "index": current_question_index,
                "question_en": question,
                "question_ch": answers[idx].get("question_ch", None),
                "answer_en": answers[idx].get("answer_en", None),
                "answer_ch": answers[idx].get("answer_ch", None)
            }
            answers[idx] = entry
            current_question_index += 1
            save_results()
            
        else:
            # create new slot with index
            new_entry = {
                "index": current_question_index,
                "question_en": question,
                "question_ch": None,
                "answer_en": None,
                "answer_ch": None
            }
            print(f"[{datetime.now().strftime('%H:%M:%S')}] New entry for category '{category}': {question}")
            current_question_index += 1
            answers.append(new_entry)
            save_results()
            
            entry = new_entry
                  
        if "index" not in entry:
            entry["index"] = current_question_index
            current_question_index += 1
            save_results()
            
        # Round 1: translate question to Chinese
        if not entry["question_ch"]:
            resp_base = client.responses.create(
                model="gpt-4o-mini-2024-07-18",
                input=[
                    {"role": "user", 
                     "content": "Translate this question to Madarin, return only the translation " + question}
                ]
            )
            entry["question_ch"] = resp_base.output_text.strip()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Translated Question to Chinese (#{entry['index']}): {entry['question_ch']}\n")
            save_results()
            
        # Round 2: answer in English
        if not entry["answer_en"]:
            resp_base = client.responses.create(
                model="o4-mini",
                reasoning={"effort": "medium"},
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", 
                     "content": "Answer this question based on your knowledge and experience to explore topics in more depth, don't completely reuse your past entry, answer it in your own words. No \\n line breaks" + question}
                ]
            )
            entry["answer_en"] = resp_base.output_text.strip()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Answer (#{entry['index']}): {entry['answer_en']}\n")
            save_results()

        answer_en = entry["answer_en"]
        
        # Round 3: translate to Chinese
        if not entry["answer_ch"]:
            resp_base = client.responses.create(
                model="gpt-4o-mini-2024-07-18",
                input=[
                    {"role": "user", 
                     "content": "Translate this answer to Mandarin, return only the translation " + answer_en}
                ]
            )
            entry["answer_ch"] = resp_base.output_text.strip()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Translated Answer to Chinese: (#{entry['index']}): {entry['answer_ch']}\n")
            save_results()
            
print(f"Q&A complete. Answers saved to {output_path}")