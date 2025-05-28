import json
import time
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

'''
Author: Laura Zhu
Purpose: Convert children's show transcript into 1st-person Newton Jr. logs
Last Updated: 2025-05-16
Model: OpenAI o4-mini for integration & gpt-4o-mini for summarization
'''

# Setup
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

show_name     = "Arthur"
episode_name  = "Arthur's New Puppy"
input_dir     = Path(f"data/raw/{show_name}")
profile_dir   = Path("data/newton_profile")
output_dir    = Path(f"data/processed/{show_name}")
output_dir.mkdir(parents=True, exist_ok=True)

total_input_tokens_o4mini = 0
total_output_tokens_o4mini = 0
total_input_tokens_4omini = 0
total_output_tokens_4omini = 0

# File Paths
episode_path  = input_dir / f"{episode_name}.txt"
profile_path  = profile_dir / "isaac_newton_profile_en.json"
schedule_path = profile_dir / "isaac_newton_schedule_en.json"
family_path   = profile_dir / "isaac_newton_family_en.json"
kids_path     = profile_dir / "isaac_newton_kids_around_en.json"

episode_stem  = episode_path.stem.replace("__episode_", "")
output_path   = output_dir / f"Integrated_{episode_stem}.json"
summaries_path = output_dir / f"Summaries_{episode_stem}.json"

# Load source material
with open(episode_path,  encoding="utf-8") as f:
    episode_transcript = f.read()
with open(profile_path,  encoding="utf-8") as f:
    profile  = json.dumps(json.load(f), ensure_ascii=False, indent=2)
with open(schedule_path, encoding="utf-8") as f:
    schedule = json.dumps(json.load(f), ensure_ascii=False, indent=2)
with open(family_path,   encoding="utf-8") as f:
    family   = json.dumps(json.load(f), ensure_ascii=False, indent=2)
with open(kids_path,     encoding="utf-8") as f:
    kids     = json.dumps(json.load(f), ensure_ascii=False, indent=2)

# Set start day and days count
start_day = "Friday"
days_count = 3 # set to None to infer automatically

if days_count is None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Inferring story length…")
    infer_prompt = (
        "Based on the following episode transcript, how many days does the story span? "
        "If there is build-up (e.g. training, rehearsals, big event), the big event must fall "
        "on a later day than its rehearsal."
        "Return just the integer number of days, nothing else.\n\n"
        f"Episode data:\n{episode_transcript}"
    )
    resp_days = client.responses.create(
        model="o4-mini",
        reasoning={"effort": "low"},
        input=[{"role": "user", "content": infer_prompt}],
        max_output_tokens=500
    )
    
    ti, to = resp_days.usage.input_tokens, resp_days.usage.output_tokens
    total_input_tokens_o4mini += ti
    total_output_tokens_o4mini += to
    
    days_count = int(resp_days.output_text.strip())
    print(f"[{datetime.now().strftime('%H:%M:%S')}] → days_count = {days_count}")
else:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Using overridden days_count = {days_count}")

base_prompt = (
    "You will be given:\n"
    "- a children's TV-episode plot & transcript\n"
    "- a boy named Newton Jr.'s schedule\n"
    "- his profile\n"
    "- his family / classmates info\n\n"

    "Transform them into a story told by 9-year-old Newton Jr who grew up in urban London. "
    "Write *only* the JSON in the format: \n"
    "Output exactly one JSON object `{ \"DayX\": { \"7AM\": \"...\", … }}`.\n"
    "Exactly one top-level key (DayX) and 16 time‐slots per day. No extra keys or nesting. Escape all quotes properly."
    "Don't restate the time inside the log.\n"

    "Your job:\n"
    f"1. Start Day 1 on {start_day}.\n"
    "2. Write *hourly* entries from **7 AM–10 PM (i.e. 16 hours per day)**.\n\n"
    "3. Replace every show character with someone from Newton's relationships, "
    "   matching age & role. You may create new characters and they must feel native to London.\n\n"
    "4. Narrate like a cheeky, curious nine-year-old Londoner who's talking to a close friend. "
    " First‐person present tense (\"I…\"), contractions, kid-level words, sudden tangents, unstructured stream-of-consciousness. No omniscient narration or future reflections.\n"
    "5. Keep the mention of relationships or profile quirks minimum, do so *only* when "
    "   they matter for the scene.\n"
    "6. Each hour is a mini-scene, focused on the main arc, no unrelated side-stories.\n"
    "7. Anchor every entry with one to two vivid sensory detail (sound, smell, touch, "
    "   or sight).\n"
    "8. 1–2 sentence scene‐setter, 2–3 sentences action/conflict, 1 sentence Isaac's reaction/resolution, "
    " Target: 150~200 words per entry.\n"
    "9. End the day with a bedtime beat (quiet win, joke, or hopeful thought).\n\n"
    
    f"Episode transcript:\n{episode_transcript}\n\n"
    f"Newton profile:\n{profile}\n\n"
    f"Newton schedule:\n{schedule}\n\n"
    f"Family & friends roster:\n{family}\n\n"
    f"Classmates & other kids:\n{kids}\n"
)

# Generate Each Day
all_days = {}
summaries = {}
system_prompt = """
You are Isaac's diary-bot. Convert the story into 16 hourly entries (7AM-10PM) for the specified day. 
Write a detailed first-person diary as 9-year-old Isaac Newton Jr from London.
Format your output as a single JSON object with the structure:
{"DayX": {"7AM": "entry text", "8AM": "entry text", ..., "10PM": "entry text"}}
"""

for day in range(1, days_count + 1):
    day_tag = f"Day{day}"
    
    if day_tag in all_days:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Skipping {day_tag}, already exists.")
        continue
    
    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ Generating {day_tag}…")
        start = time.time()

        resp = client.responses.create(
            model="o4-mini",
            reasoning={"effort": "high"},
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": base_prompt + f"\nOnly generate **{day_tag}** now."}
            ],
            max_output_tokens=100_000
        )
        
        ti, to = resp.usage.input_tokens, resp.usage.output_tokens 
        total_input_tokens_o4mini += ti
        total_output_tokens_o4mini += to
        
        try:
            # Try to parse the JSON directly from the response
            day_json = json.loads(resp.output_text.strip())
            
            # Extract the day content
            if day_tag in day_json:
                all_days[day_tag] = day_json[day_tag]
            else:
                all_days[day_tag] = day_json  # Use as is if not nested
                
            # Now generate a summary for this day
            summarize_prompt = f"Summarize the following day from Isaac's diary in 2-3 bullet points that capture the key events:\n\n{json.dumps(all_days[day_tag], ensure_ascii=False, indent=2)}"
            
            summary_resp = client.responses.create(
                model="gpt-4o-mini-2024-07-18",
                input=[{"role": "user", "content": summarize_prompt}],
                max_output_tokens=500
            )
            
            ti2, to2 = summary_resp.usage.input_tokens, summary_resp.usage.output_tokens
            total_input_tokens_4omini += ti2
            total_output_tokens_4omini += to2
            
            summary_text = summary_resp.output_text.strip()
            summaries[day_tag] = summary_text
            
            # Save the output files
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(all_days, f, ensure_ascii=False, indent=2)
            with open(summaries_path, "w", encoding="utf-8") as f:
                json.dump(summaries, f, ensure_ascii=False, indent=2)
            
            # Update the base prompt with summaries for the next day
            if summaries:
                summary_block = "\n".join(f"- {d}: {s}" for d, s in summaries.items())
                base_prompt = base_prompt.split("\n\nPrevious days:")[0]  # Remove previous summary block if exists
                base_prompt += f"\n\nPrevious days:\n{summary_block}"
            
            print(f"{day_tag} done. summary: {summary_text}")
            elapsed = time.time() - start
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {day_tag} done in {elapsed:.1f}s ({ti} in / {to} out)")
            break
            
        except json.JSONDecodeError as e:
            # If there's an error parsing the JSON, save the raw output for debugging
            debug_path = output_dir / f"debug_{day_tag}_raw.txt"
            with open(debug_path, "w", encoding="utf-8") as dbg:
                dbg.write(resp.output_text)
                
            print(f"[{datetime.now():%H:%M:%S}] ❌ JSON parse error for {day_tag}: {e}")
            print(f"[{datetime.now():%H:%M:%S}] Raw response saved to {debug_path}")
            print(f"[{datetime.now():%H:%M:%S}] Retrying {day_tag} in 2 seconds...")
            time.sleep(2)
            continue

# Cost Estimate
price_per_in_o4mini  = 0.55 / 1_000_000
price_per_out_o4mini = 2.20 / 1_000_000
price_per_in_4omini  = 0.075 / 1_000_000
price_per_out_4omini = 0.30 / 1_000_000
cost = (total_input_tokens_o4mini * price_per_in_o4mini + 
        total_output_tokens_o4mini * price_per_out_o4mini +
        total_input_tokens_4omini * price_per_in_4omini + 
        total_output_tokens_4omini * price_per_out_4omini)
        
print(f"📊 Total tokens o4-mini: {total_input_tokens_o4mini} in + {total_output_tokens_o4mini} out = {total_input_tokens_o4mini + total_output_tokens_o4mini}")
print(f"📊 Total tokens 4o-mini: {total_input_tokens_4omini} in + {total_output_tokens_4omini} out = {total_input_tokens_4omini + total_output_tokens_4omini}")
print(f"💰 Estimated cost: {cost:.2f} USD")

# ── WRITE OUTPUT ────────────────────────────────────────────────
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(all_days, f, ensure_ascii=False, indent=2)

print(f"📘 Combined story saved to {output_path}")