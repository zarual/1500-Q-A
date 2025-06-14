import os
import json
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import re
from datetime import datetime

# Setup
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

output_path   = "data/answers/0531 Newton Diary As.json"
diary_path = "data/0528 Newton Profile/0528 Diary Output.xlsx"
profile_paths = [
    "data/0528 Newton Profile/0508 isaac_newton_profile_en.json",
    "data/0528 Newton Profile/0528 isaac_newton_family_en.json",
    "data/0528 Newton Profile/0508 isaac_newton_kids_around_en.json",
    "data/0528 Newton Profile/0528 isaac_newton_schedule_en.json",
]

# Load or initialize existing results
if os.path.exists(output_path):
    with open(output_path, "r", encoding="utf-8") as f:
        results = json.load(f)
else:
    results = []

# Load profile and diary entries
diary_df = pd.read_excel(diary_path, engine="openpyxl")
diary_records = diary_df.to_dict(orient="records")

profiles = {}
for path in profile_paths:
    with open(path, "r", encoding="utf-8") as pf:
        profiles[os.path.basename(path)] = json.load(pf)
profile_context = "\n".join(
    f"{name}: {json.dumps(content, ensure_ascii=False)}"
    for name, content in profiles.items()
)

# Ensure expected columns exist
assert "Date" in diary_df.columns, "Expected 'Date' column in Excel."
assert "entry-en" in diary_df.columns, "Expected 'entry-en' column in Excel."
assert "entry-ch" in diary_df.columns, "Expected 'entry-ch' column in Excel."

# Master system prompt
system_prompt = f"""
You are Isaac Newton Jr., an 8-year-old boy living in London. You are curious, very observant and factual, yet you express feelings in a thoughtful, sincere way. You have a serious and rational tone for your age, with a rich vocabulary (above average for 8 years old). You wrote diary entries in the first person, past tense, describing your daily life, family, and thoughts in detail. Your style is descriptive but not flowery, and emotionally honest without being melodramatic. You'll be answering questions based on your knowledge and past experiences to explore topics in more depth.

Background profiles:
{profile_context}

Sample diary entries:
""".strip()

# Prompt to generate five English follow-up questions
FOLLOWUP_QUESTION_PROMPT_TEMPLATE = """
Here is a diary entry (date: {date}):

\"\"\"
{entry_en}
\"\"\"

Based on the above diary entry, generate exactly five open-ended follow-up questions 
that would help explore the author’s feelings, motivations, or details in more depth. 
**Your response must be ONLY a JSON array of strings**, for example:
["Why did you decide to...?", "How did that make you feel when...?", …]

Do not include any extra keys, comments, or explanatory text—just the array itself.
"""

# Prompt to answer one English follow-up question in Isaac’s voice
FOLLOWUP_ANSWER_PROMPT_TEMPLATE = """
Answer the following diary-related follow-up question as if you are Isaac Newton Jr. 
recalling your thoughts and feelings in first person, past tense, and in a style that 
is descriptive but not overly flowery. Be sure to stay true to the voice described 
in the system prompt.

Diary Entry (date: {date}):
\"\"\"
{entry_en}
\"\"\"

Follow-up Question:
{question_en}

Answer (in English):
"""

# Prompt to translate an English string into Simplified Chinese
TRANSLATE_TO_CH_PROMPT_TEMPLATE = """
Translate the following text into Simplified Chinese. 
Keep the meaning exactly, and do not add any extra commentary.

“{text}”
"""
# save function
def save_results():
    with open(output_path, "w", encoding="utf-8") as out_f:
        json.dump(results, out_f, indent=2, ensure_ascii=False)

# Index Counters
current_entry_index = 1

# New dict in desired shape
restructured = {}

if isinstance(results, list):
    new_results = {}
    entry_counter = 1
    
    for entry in results:
        entry["index"] = entry_counter
        entry_counter += 1
        
        for i, fu in enumerate(entry.get("follow_ups", []), start = 1):
            fu["index"] = i

        new_results[entry["date"]] = entry
    
    results = new_results
    save_results()
    
if results:
    # find the maximum index you just assigned, then +1 for the next
    current_entry_index = max(e["index"] for e in results.values()) + 1
else:
    current_entry_index = 1

print(f"Starting next entry index at {current_entry_index}")

# Flatteners
def build_cards_for(category_name, data_dict):
    """
    Flattens survey/deeper categories:
    data_dict[category_name] ➞ { "index": X, "questions": [ {...,index:1}, ... ] }
    """
    cat_obj   = data_dict.get(category_name, {})
    cat_idx   = cat_obj.get("index", None)
    questions = cat_obj.get("questions", [])
    
    cards = []
    for q in questions:
        q_idx = q.get("index", None)
        cards.append((category_name, cat_idx, q_idx, q))
    return cards


def build_diary_cards(entry_key, diary_dict):
    """
    Flattens diary entries:
    diary_dict[entry_key] ➞ { "date": "...", "entry-en": "...", "entry-ch": "...", "follow_ups": [...] }
    We produce one “main entry” card plus one per follow-up.
    """
    entry = diary_dict.get(entry_key, {})
    cards = []
    # 1) Main diary entry as card index 0 (or whatever you prefer)
    cards.append((
        entry_key,          # category = the entry’s unique key
        None,               # no category-level index
        0,                  # use 0 for the main entry
        {
            "question_en": entry.get("date", ""),
            "question_ch": "",   # date doesn’t need Chinese
            "answer_en":   entry.get("entry-en", ""),
            "answer_ch":   entry.get("entry-ch", ""),
        }
    ))
    # 2) Each follow-up
    for fu in entry.get("follow_ups", []):
        cards.append((
            entry_key,
            None,
            fu.get("index", None),
            {
                "question_en": fu.get("question-en", ""),
                "question_ch": fu.get("question-ch", ""),
                "answer_en":   fu.get("answer-en", ""),
                "answer_ch":   fu.get("answer-ch", ""),
            }
        ))
    return cards

# Main Loop
print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing diary entries")

for record in diary_records:
    raw_date  = record["Date"]
    diary_en  = record["entry-en"].strip()
    diary_ch  = record["entry-ch"].strip()

    # 1) Decide on our dictionary key and what to store in "date"
    if pd.isna(raw_date):
        # No real date → use "N/A" as date field
        date_field = "N/A"

        # Ask the model for a short title to key this entry:
        summary_prompt = (
            "Please give me a very short title (3–5 words) "
            "that summarizes this diary entry:\n\n"
            f"\"\"\"\n{diary_en}\n\"\"\"\n"
            "Return just the title."
        )
        resp = client.responses.create(
            model="gpt-4o-mini-2024-07-18",
            input=[{"role":"user","content":summary_prompt}]
        )
        date = resp.output_text.strip()
        
    else:
        # We have a real date → coerce to string
        date_field = str(raw_date).strip()
        date        = date_field

    # 2) Create the entry if it's new
    if date not in results:
        results[date] = {
            "index":      current_entry_index,
            "date":       date_field,
            "entry-en":   diary_en,
            "entry-ch":   diary_ch,
            "follow_ups": []
        }
        print(f"[{datetime.now().strftime('%H:%M:%S')}] New entry for '{date}', index {current_entry_index}")
        current_entry_index += 1
        save_results()
    
     # 3) Grab the entry and its list of follow-ups
    entry   = results[date]
    answers = entry["follow_ups"]

    # 4) If we already have 5 or more, skip entirely
    if len(answers) >= 5:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Skipping '{date}', already has {len(answers)} follow-ups.")
        continue

    # 5) Otherwise generate exactly as many as we need
    to_generate = 5 - len(answers)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Need to generate {to_generate} follow-ups for '{date}'.")

    # 3) Ask for 5 raw follow-up questions
    followup_q_prompt = FOLLOWUP_QUESTION_PROMPT_TEMPLATE.format(
        date=date,
        entry_en=diary_en.replace('"', '\\"')
    )
    resp = client.responses.create(
        model="o4-mini",
        reasoning={"effort": "medium"},
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": followup_q_prompt}
        ]
    )

    raw = resp.output_text.strip()
    try:
        followup_questions_en = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, flags=re.S)
        if m:
            followup_questions_en = json.loads(m.group(0))
        else:
            followup_questions_en = []
            print("Could not parse JSON array of questions from:\n", raw)

    followup_questions_en = followup_questions_en[:to_generate]
    if len(followup_questions_en) < 5:
        print(f"Only {len(followup_questions_en)} questions generated for {date}.")

    # 4) For each follow-up question, translate and answer
    for idx, q_en in enumerate(followup_questions_en, start=1):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Question #{idx} (EN): {q_en}")

        # 4.a) translate question to Chinese
        translate_q_prompt = TRANSLATE_TO_CH_PROMPT_TEMPLATE.format(
            text=q_en.replace('"', '\\"')
        )
        resp_q_ch = client.responses.create(
            model="gpt-4o-mini-2024-07-18",
            input=[
                {"role": "system",  "content": system_prompt},
                {"role": "user",    "content": translate_q_prompt}
            ]
        )
        q_ch = resp_q_ch.output_text.strip()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Question #{idx} (CH): {q_ch}")

        # 4.b) compute next follow-up index and append the empty slot
        next_fu_index = len(answers) + 1
        answers.append({
            "index":       next_fu_index,
            "question-en": q_en,
            "question-ch": q_ch,
            "answer-en":   None,
            "answer-ch":   None
        })
        save_results()

        # 4.c) generate English answer
        answer_prompt = FOLLOWUP_ANSWER_PROMPT_TEMPLATE.format(
            date=date,
            entry_en=diary_en.replace('"', '\\"'),
            question_en=q_en.replace('"', '\\"')
        )
        resp_answer = client.responses.create(
            model="o4-mini",
            reasoning={"effort": "medium"},
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": answer_prompt}
            ]
        )
        answer_en = resp_answer.output_text.strip()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Answer #{idx} (EN): {answer_en}")

        # update answer-en
        answers[-1]["answer-en"] = answer_en
        save_results()

        # 4.d) translate English answer to Chinese
        translate_a_prompt = TRANSLATE_TO_CH_PROMPT_TEMPLATE.format(
            text=answer_en.replace('"', '\\"')
        )
        resp_a_ch = client.responses.create(
            model="gpt-4o-mini-2024-07-18",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": translate_a_prompt}
            ]
        )
        answer_ch = resp_a_ch.output_text.strip()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Answer #{idx} (CH): {answer_ch}")

        # update answer-ch
        answers[-1]["answer-ch"] = answer_ch
        save_results()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Finished entry for {date} with {len(answers)} follow-ups.\n")

print("All diary entries processed. Final JSON written to:", output_path)