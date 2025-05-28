import json
import streamlit as st
from openai import OpenAI
import os

# ─── Config ─────────────────────────────────────────────────────────────────
openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
INPUT_PATH  = "data/0528 Newton 1500 Q&A answered.json"
OUTPUT_PATH = "data/0528 Newton 1500 Q&A filtered.json"

# ─── Load Q&A ───────────────────────────────────────────────────────────────
@st.cache_data
def load_qa():
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
qa_data = load_qa()

# Flatten cards to (category, idx, entry)
cards = []
for cat, entries in qa_data.items():
    for i, ent in enumerate(entries):
        cards.append((cat, i, ent))

# ─── Session State ─────────────────────────────────────────────────────────
if "card_idx" not in st.session_state:
    st.session_state.card_idx = 0
if "stage" not in st.session_state:
    st.session_state.stage = "base"   # or "followup"
if "kept" not in st.session_state:
    st.session_state.kept = {cat: [] for cat in qa_data}
if "current_followups" not in st.session_state:
    st.session_state.current_followups = []
if "followup_idx" not in st.session_state:
    st.session_state.followup_idx = 0

# ─── Translation Helper ────────────────────────────────────────────────────
def translate_cn(en: str) -> str:
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system", "content":"Translate the below English into Simplified Chinese only."},
            {"role":"user",   "content": en}
        ]
    )
    return resp.choices[0].message.content.strip()

# ─── Download Helper ────────────────────────────────────────────────────

def get_filtered_json():
    filtered = {
        cat: lst
        for cat, lst in st.session_state.kept.items()
        if lst
    }
    return json.dumps(filtered, ensure_ascii=False, indent=2)

# ─── App UI ─────────────────────────────────────────────────────────────────
st.title("🔍 Memory Review")

if st.session_state.card_idx < len(cards):
    cat, idx, entry = cards[st.session_state.card_idx]

    if st.session_state.stage == "base":
        # --- Base Q&A ---
        st.header(f"{cat}  —  {st.session_state.card_idx+1}/{len(cards)}")
        st.markdown(f"**Q:** {entry['question']}")
        st.markdown(f"**A:** {entry['answer']}")
        # Chinese translation immediately below
        st.markdown(f"**问：** {translate_cn(entry['question'])}")
        st.markdown(f"**答：** {translate_cn(entry['answer'])}")

        col1, col2, col3 = st.columns([3,3,2])
        if col1.button("👍 Keep"):
            st.session_state.current_followups = entry.get("follow_ups", [])
            st.session_state.followup_idx = 0
            st.session_state.stage = "followup"
        if col2.button("👎 Discard"):
            st.session_state.card_idx += 1
        with col3:
                st.download_button(
                    label="💾 Save progress",
                    data=get_filtered_json(),
                    file_name="0528_Newton_QA_progress.json",
                    mime="application/json"
                )
            # remains in "base" stage

    else:
        # --- Follow-up Q&A ---
        fups = st.session_state.current_followups
        if st.session_state.followup_idx < len(fups):
            fq = fups[st.session_state.followup_idx]
            st.subheader(f"Follow-up {st.session_state.followup_idx+1}/{len(fups)}")
            st.markdown(f"**Q:** {fq['question']}")
            st.markdown(f"**A:** {fq['answer']}")

            st.markdown(f"**问：** {translate_cn(fq['question'])}")
            st.markdown(f"**答：** {translate_cn(fq['answer'])}")

            col1, col2, col3 = st.columns([3,3,2])
            if col1.button("👍 Keep"):
                # If first follow-up, create new entry; else append
                if st.session_state.followup_idx == 0:
                    st.session_state.kept[cat].append({
                        "question": entry["question"],
                        "answer":  entry["answer"],
                        "follow_ups": [fq]
                    })
                else:
                    st.session_state.kept[cat][-1]["follow_ups"].append(fq)
                st.session_state.followup_idx += 1

            if col2.button("👎 Discard"):
                st.session_state.followup_idx += 1
                
            with col3:
                st.download_button(
                    label="💾 Save progress",
                    data=get_filtered_json(),
                    file_name="0528_Newton_QA_progress.json",
                    mime="application/json"
    )

        else:
            # Done with this card’s follow-ups
            st.session_state.card_idx += 1
            st.session_state.stage = "base"

else:
    # --- Finished Reviewing ---
    st.success("🎉 Review complete!")
    filtered = {c: lst for c, lst in st.session_state.kept.items() if lst}
    out_json = json.dumps(filtered, ensure_ascii=False, indent=2)
    st.download_button(
        "⬇️ Download filtered Q&A JSON",
        out_json,
        file_name=OUTPUT_PATH,
        mime="application/json"
    )
