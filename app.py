import json
import streamlit as st

# 1️⃣ Load your Q&A JSON
DATA_PATH = "0528 Newton 1500 Q&A answered.json"
with open(DATA_PATH, "r", encoding="utf-8") as f:
    qa_data = json.load(f)

# 2️⃣ Flatten to a list of entries
cards = []
for cat, entries in qa_data.items():
    for entry in entries:
        cards.append({
            "category": cat,
            "question": entry["question"],
            "answer": entry["answer"]
        })

# 3️⃣ Session state to remember where we are
if "idx" not in st.session_state:
    st.session_state.idx = 0
if "kept" not in st.session_state:
    st.session_state.kept = []
if "rejected" not in st.session_state:
    st.session_state.rejected = []

# 4️⃣ Show one card at a time
idx = st.session_state.idx
if idx < len(cards):
    card = cards[idx]
    st.markdown(f"### ({idx+1}/{len(cards)})  **{card['category']}**")
    st.markdown(f"**Q:** {card['question']}")
    st.markdown(f"**A:** {card['answer']}")
    st.write("---")

    # 5️⃣ Yes / No buttons
    col1, col2 = st.columns(2)
    if col1.button("👍 Keep"):
        st.session_state.kept.append(card)
        st.session_state.idx += 1
    if col2.button("👎 Discard"):
        st.session_state.rejected.append(card)
        st.session_state.idx += 1

else:
    st.success("🏁 You’ve reviewed all cards!")
    st.write(f"Kept: {len(st.session_state.kept)}  Discarded: {len(st.session_state.rejected)}")

    # 6️⃣ Download the filtered JSON
    kept_json = json.dumps(st.session_state.kept, ensure_ascii=False, indent=2)
    st.download_button(
        "⬇️ Download Kept Entries",
        kept_json,
        file_name="kept_memories.json",
        mime="application/json"
    )
