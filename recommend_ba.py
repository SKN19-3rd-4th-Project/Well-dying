import os
import json
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------------
# 1. 규칙 로드 (conversation_rules.json)
# ------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(BASE_DIR, "data", "conversation_rules.json")

# ✨ 파일 존재 여부 체크
if not os.path.exists(RULES_PATH):
    logging.error(f"conversation_rules.json을 찾을 수 없습니다: {RULES_PATH}")
    RULES = {"mappings": {"emotion_to_feeling_tags": {}, "mobility_to_energy_range": {}}}
else:
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        RULES = json.load(f)


# ------------------------------------------------------------
# 2. 매핑 함수 (감정 → FEELING_TAGS, 기동성 → 에너지)
# ------------------------------------------------------------

def map_emotion_to_feelings(b1_answer: str) -> list[str]:
    """B1(현재 마음) 답변을 FEELING_TAGS 리스트로 매핑"""
    if not b1_answer:
        logging.warning("B1(감정) 값이 비어있습니다.")
        return []
    
    mapping = RULES.get("mappings", {}).get("emotion_to_feeling_tags", {})
    result = mapping.get(b1_answer, [])
    
    if not result:
        logging.warning(f"B1 '{b1_answer}'에 해당하는 감정 태그가 없습니다.")
    
    return result


def map_mobility_to_energy_range(a4_answer: str) -> tuple[int, int]:
    """A4(움직임/기동성) 답변을 ENERGY_REQUIRED 범위(min,max)로 매핑"""
    if not a4_answer:
        logging.warning("A4(기동성) 값이 비어있습니다. 기본 범위(1-2) 사용.")
        return 1, 2
    
    mapping = RULES.get("mappings", {}).get("mobility_to_energy_range", {})
    info = mapping.get(a4_answer)
    
    if info is None:
        logging.warning(f"A4 '{a4_answer}'에 해당하는 에너지 범위가 없습니다. 기본 범위(1-2) 사용.")
        return 1, 2
    
    return info.get("min_energy", 1), info.get("max_energy", 2)


# ------------------------------------------------------------
# 3. ⭐ 새로운 추천 로직: 의미 수준 기반
# ------------------------------------------------------------

def recommend_activities_from_user_profile(
    user_answers: dict, 
    activities_df: pd.DataFrame,
    conversation_stage: str = "early"
) -> pd.DataFrame:
    """
    사용자 프로필과 대화 단계에 따라 의미 있는 활동 추천
    
    Args:
        user_answers: 프로필 정보 (B1, A4 포함)
        activities_df: meaningful_activities.csv
        conversation_stage: "early" | "middle" | "late"
    
    Returns:
        추천 활동 DataFrame (최대 3개)
    """
    
    # ✨ 필수 키 검증
    if "B1" not in user_answers or "A4" not in user_answers:
        logging.error(f"필수 키(B1, A4)가 없습니다: {user_answers.keys()}")
        return pd.DataFrame()
    
    # ✨ activities_df 검증
    if activities_df.empty:
        logging.error("activities_df가 비어있습니다.")
        return pd.DataFrame()
    
    required_cols = ["ENERGY_REQUIRED", "FEELING_TAGS", "activity_kr", "meaning_level", "category"]
    missing_cols = set(required_cols) - set(activities_df.columns)
    if missing_cols:
        logging.error(f"activities_df에 필수 컬럼이 없습니다: {missing_cols}")
        return pd.DataFrame()

    # B1: 감정 → FEELING_TAGS
    b1 = user_answers.get("B1")
    target_feelings = map_emotion_to_feelings(b1)

    # A4: 기동성 → 에너지 범위 (최대 2까지만)
    a4 = user_answers.get("A4")
    min_energy, max_energy = map_mobility_to_energy_range(a4)

    # ✨ 대화 단계별 의미 수준 필터
    if conversation_stage == "early":
        # 초기: 감각, 휴식만 (meaning_level 1)
        allowed_categories = ["감각", "휴식"]
        max_meaning = 1
    elif conversation_stage == "middle":
        # 중기: 회상, 연결 추가 (meaning_level 1-2)
        allowed_categories = ["감각", "휴식", "회상", "연결"]
        max_meaning = 2
    else:  # late
        # 후기: 유산, 성찰 포함 (meaning_level 1-3)
        allowed_categories = ["감각", "휴식", "회상", "연결", "유산", "성찰"]
        max_meaning = 3

    # --------------------------------------
    # 1) 에너지 필터
    # --------------------------------------
    cand = activities_df[
        (activities_df["ENERGY_REQUIRED"] >= min_energy) &
        (activities_df["ENERGY_REQUIRED"] <= max_energy)
    ].copy()

    if cand.empty:
        logging.warning(f"에너지 범위({min_energy}-{max_energy})에 맞는 활동이 없습니다.")
        return pd.DataFrame()

    # --------------------------------------
    # 2) 카테고리 필터
    # --------------------------------------
    cand = cand[cand["category"].isin(allowed_categories)].copy()
    
    if cand.empty:
        logging.warning(f"카테고리({allowed_categories})에 맞는 활동이 없습니다.")
        return pd.DataFrame()

    # --------------------------------------
    # 3) 의미 수준 필터
    # --------------------------------------
    cand = cand[cand["meaning_level"] <= max_meaning].copy()

    # --------------------------------------
    # 4) 감정 태그 매칭 (선호도 점수)
    # --------------------------------------
    def calculate_score(row):
        score = row["meaning_level"]  # 기본 점수 = 의미 수준
        
        # 감정 태그 일치하면 +1
        if target_feelings and pd.notna(row["FEELING_TAGS"]):
            for tf in target_feelings:
                if tf in str(row["FEELING_TAGS"]):
                    score += 1
                    break
        
        return score
    
    cand["score"] = cand.apply(calculate_score, axis=1)

    # --------------------------------------
    # 5) 정렬 후 상위 3개 반환
    # --------------------------------------
    cand = cand.sort_values("score", ascending=False).reset_index(drop=True)
    
    logging.info(f"대화 단계: {conversation_stage}, 후보 활동: {len(cand)}개")
    return cand


# ------------------------------------------------------------
# 4. 추천 메시지 포맷팅 (간소화)
# ------------------------------------------------------------

def format_recommendation_message(user_answers: dict, rec_df: pd.DataFrame) -> str:
    """
    추천된 활동들을 간단한 텍스트로 정리
    LLM이 자연스럽게 변환할 수 있도록 최소한의 정보만
    """
    
    if rec_df.empty:
        return "지금 조건에 맞는 활동을 찾지 못했어요."
    
    emotion = user_answers.get("B1", "")
    
    lines = [f"현재 마음: {emotion}"]
    lines.append("")
    lines.append("추천 활동:")
    
    for idx, row in rec_df.iterrows():
        name = row.get("activity_kr", "")
        category = row.get("category", "")
        meaning = row.get("meaning_level", 1)
        
        # 의미 수준 설명
        meaning_desc = {
            1: "편안한",
            2: "의미 있는", 
            3: "깊은 의미의"
        }.get(meaning, "")
        
        lines.append(f"- {name} ({meaning_desc}, {category})")
    
    return "\n".join(lines)