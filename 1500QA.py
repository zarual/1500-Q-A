import os
import json
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

# Setup
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load Q&A file
with open("data/0528 Newton 1500 Q&A.json", "r", encoding="utf-8") as f:
    qa_data = json.load(f)

# Load diary Excel (sheet named "2016—2022")
diary_df = pd.read_excel("data/0528 Diary Output.xlsx", engine="openpyxl")
diary_entries = diary_df.to_dict(orient="records")
diary_context = json.dumps(diary_entries, ensure_ascii=False)

# Load profile context JSON files
profile_paths = [
    "data/0528 Newton Profile/0508 isaac_newton_kids_around_en.json",
    "data/0528 Newton Profile/0528 isaac_newton_family_en.json",
    "data/0528 Newton Profile/0528 isaac_newton_schedule_en.json",
]
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
You are Isaac Newton Jr., an 8-year-old boy living in London. You are curious, very observant and factual, yet you express feelings in a thoughtful, sincere way. You have a serious and rational tone for your age, with a rich vocabulary (above average for 8 years old). You write diary entries in the first person, past tense, describing your daily life, family, and thoughts in detail. Your style is descriptive but not flowery, and emotionally honest without being melodramatic.

Background profiles:
{profile_context}

Sample diary entries:
{diary_context}
""".strip()

results = {}

# Iterate through each category
for category, content in qa_data.items():
    results[category] = []
    base_questions = content["questions"]
    follow_up_pool = content["follow_up_questions"]

    # Process the first 10 base questions in this category
    for question in base_questions[:10]:
        # Round 1: Answer the base question
        resp_base = client.responses.create(
            model="o4-mini",
            reasoning={"effort": "medium"},
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
        )
        base_answer = resp_base.choices[0].message.content.strip()

        # Round 2a: Select 10 most appropriate follow-up questions
        selection_prompt = (
            f"Based on this answer:\n\"{base_answer}\"\n\n"
            "Select the 10 most appropriate follow-up questions from the list below. "
            "Return a JSON array containing only the selected questions:\n\n" +
            "\n".join(f"- {fq}" for fq in follow_up_pool)
        )
        resp_select = client.responses.create(
            model="o4-mini",
            reasoning={"effort": "medium"},
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": selection_prompt}
            ]
        )
        selected_follow_ups = json.loads(resp_select.choices[0].message.content)

        # Round 2b: Answer each selected follow-up question
        follow_up_results = []
        for fq in selected_follow_ups:
            resp_fq = client.responses.create(
                model="o4-mini",
                reasoning={"effort": "medium"},
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": fq}
                ]
            )
            follow_up_results.append({
                "question": fq,
                "answer": resp_fq.choices[0].message.content.strip()
            })

        # Save results
        results[category].append({
            "question": question,
            "answer": base_answer,
            "follow_ups": follow_up_results
        })

# Write output
output_path = "0528 Newton 1500 Q&A answered.json"
with open(output_path, "w", encoding="utf-8") as out_f:
    json.dump(results, out_f, indent=2, ensure_ascii=False)

print(f"Q&A complete. Answers saved to {output_path}")
