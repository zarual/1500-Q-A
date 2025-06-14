import json
import streamlit as st
import base64

# ─── Config ─────────────────────────────────────────────────────────────────
SURVEY_INPUT_PATH   = "data/answers/0531 Newton 750 Survey As.json"
SURVEY_OUTPUT_PATH  = "data/filtered/0531 Newton 750 Survey As.json"
DEEPER_INPUT_PATH   = "data/answers/0531 Newton Deeper As.json"
DEEPER_OUTPUT_PATH  = "data/filtered/0531 Newton Deeper As.json"
DIARY_INPUT_PATH    = "data/answers/0531 Newton Diary As.json"
DIARY_OUTPUT_PATH   = "data/filtered/0531 Newton Diary As.json"

# ─── Load JSONs once ──────────────────────────────────────────────────────────
@st.cache_data
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

survey_data = load_json(SURVEY_INPUT_PATH)
deeper_data = load_json(DEEPER_INPUT_PATH)
diary_data  = load_json(DIARY_INPUT_PATH)

# ─── Global CSS: white Georgia text ───────────────────────────────────────────
st.markdown("""
<style>
  .white-text {
    color: #ffffff !important;
    font-family: Georgia, serif !important;
  }
  .white-h2 {
    color: #ffffff !important;
    font-family: Georgia, serif !important;
    font-size: 2rem;
    margin-bottom: 0.5rem;
  }
  .white-h3 {
    color: #ffffff !important;
    font-family: Georgia, serif !important;
    font-size: 1.25rem;
    margin-top: 1rem;
    margin-bottom: 0.25rem;
  }
</style>
""", unsafe_allow_html=True)

# ─── Builders ────────────────────────────────────────────────────────────────
def build_cards_for(category_name, data_dict):
    """Survey/Deeper pages: flatten each `questions` list."""
    cat_obj   = data_dict.get(category_name, {})
    cat_idx   = cat_obj.get("index")
    cards = []
    for q in cat_obj.get("questions", []):
        cards.append((category_name, cat_idx, q.get("index"), q))
    return cards

def build_diary_cards(entry_key, diary_dict):
    """Diary page: only flatten its `follow_ups`; main entry shown separately."""
    entry = diary_dict.get(entry_key, {})
    cat_idx = entry.get("index")
    cards = []
    for fu in entry.get("follow_ups", []):
        cards.append((entry_key, cat_idx, fu.get("index"), fu))
    return cards

# ─── Session state init ──────────────────────────────────────────────────────
if "kept" not in st.session_state:
    st.session_state.kept = {
        "750 Survey-Style Q&A": {cat: [] for cat in survey_data.keys()},
        "328 Personal Q&A":     {cat: [] for cat in deeper_data.keys()},
        "845 Diary Q&A":        {cat: [] for cat in diary_data.keys()},
    }
for p in ["survey", "deeper", "diary"]:
    key = f"card_idx_{p}"
    if key not in st.session_state:
        st.session_state[key] = 0

# ─── Background image ────────────────────────────────────────────────────────
def set_background(path):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    st.markdown(f"""
    <style>
      .stApp {{
        background: url("data:image/png;base64,{b64}") no-repeat center center fixed;
        background-size: cover;
      }}
    </style>
    """, unsafe_allow_html=True)

set_background("data/image/Cloud.png")

# ─── Sidebar: page selector & resume ─────────────────────────────────────────
page = st.sidebar.radio(
    "", 
    options=["750 Survey-Style Q&A", "328 Personal Q&A", "845 Diary Q&A"],
    index=0,
    label_visibility="collapsed"
)
st.session_state.page = page

# pick data, builder, state‐key, kept bucket, output path
if page == "750 Survey-Style Q&A":
    data_dict, builder = survey_data, build_cards_for
    idx_key = "card_idx_survey"
    kept_bucket = st.session_state.kept[page]
    output_path = SURVEY_OUTPUT_PATH
elif page == "328 Personal Q&A":
    data_dict, builder = deeper_data, build_cards_for
    idx_key = "card_idx_deeper"
    kept_bucket = st.session_state.kept[page]
    output_path = DEEPER_OUTPUT_PATH
else:
    data_dict, builder = diary_data, build_diary_cards
    idx_key = "card_idx_diary"
    kept_bucket = st.session_state.kept[page]
    output_path = DIARY_OUTPUT_PATH

# ─── Build cards ─────────────────────────────────────────────────────────────
cards = []
for key in data_dict.keys():
    cards.extend(builder(key, data_dict))

# ─── Callbacks ───────────────────────────────────────────────────────────────
def save_kept_indices():
    return json.dumps(st.session_state.kept[page], ensure_ascii=False, indent=2)

def keep_and_next(cat, q_idx):
    st.session_state.kept[page][cat].append(q_idx)
    st.session_state[idx_key] += 1

def just_next():
    st.session_state[idx_key] += 1

def jump_to(n:int):
    st.session_state[idx_key] = n - 1
    st.session_state.kept[page] = {c:[] for c in kept_bucket.keys()}

# ─── Sidebar resume widget ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Resume from")
    if cards:
        c1, c2 = st.columns((3,1))
        to = c1.number_input("", min_value=1, max_value=len(cards), value=1,
                             label_visibility="collapsed")
        c2.button("🔄", on_click=jump_to, args=(to,))

# ─── Main UI ─────────────────────────────────────────────────────────────────
# Title
st.markdown(f"<h2 class='white-h2'>{page}</h2>", unsafe_allow_html=True)

card_idx = st.session_state[idx_key]

# For Diary: show the main entry at top before any follow-up
if page == "845 Diary Q&A" and card_idx < len(cards):
    entry_key = cards[card_idx][0]
    entry = diary_data[entry_key]
    st.markdown(f"<h3 class='white-h3'>{entry['date']}</h3>", unsafe_allow_html=True)
    st.markdown(f"<div class='white-text'>{entry['entry-en']}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='white-text'>{entry['entry-ch']}</div>", unsafe_allow_html=True)
    st.markdown("---", unsafe_allow_html=True)

# Show current card (survey, deeper, or diary follow-up)
if card_idx < len(cards):
    cat, cat_idx, q_idx, q = cards[card_idx]

    # Header
    if page == "845 Diary Q&A":
        header = f"Follow-up {q_idx}  ({card_idx+1}/{len(cards)})"
    else:
        header = f"{cat} — Q{q_idx}  ({card_idx+1}/{len(cards)})"
    st.markdown(f"<h3 class='white-h3'>{header}</h3>", unsafe_allow_html=True)

    # Q&A
    # survey/deeper keys use 'question_en', 'answer_en' etc.
    # diary follow-ups use 'question-en', 'answer-en', etc.
    def mk(k): return q.get(k) or q.get(k.replace("_","-"), "")
    st.markdown(f"<div class='white-text'>Q (EN): {mk('question_en')}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='white-text'>A (EN): {mk('answer_en')}</div>",   unsafe_allow_html=True)
    st.markdown(f"<div class='white-text'>问：{mk('question_ch')}</div>",    unsafe_allow_html=True)
    st.markdown(f"<div class='white-text'>答：{mk('answer_ch')}</div>",      unsafe_allow_html=True)

    # Buttons
    c1, c2, c3 = st.columns((3,3,2))
    c1.button("🍎 Keep", key=f"keep_{page}_{cat_idx}_{q_idx}",
              on_click=keep_and_next, args=(cat, q_idx))
    c2.button("🍏 Discard", key=f"disc_{page}_{cat_idx}_{q_idx}",
              on_click=just_next)
    with c3:
        st.download_button("💾 Save progress",
                           data=save_kept_indices(),
                           file_name=f"Progress_{page.replace(' ','_')}.json",
                           mime="application/json",
                           key=f"dl_{page}_{cat_idx}_{q_idx}")

else:
    st.success(f"🎉 Review complete for “{page}”!")
    st.download_button("⬇️ Download final indices",
                       data=save_kept_indices(),
                       file_name=output_path,
                       mime="application/json",
                       key="dl_final")
