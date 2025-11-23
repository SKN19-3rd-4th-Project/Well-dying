import os
import glob
import json
import pandas as pd
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 설정
BASE_DIR = "/Users/souluk/SKN_19/SKN_19_STUDY/well_dying/legacy_data_raw/data/processed"
OUTPUT_FILE = "unified_well_dying_data.jsonl"

# 입력 경로 및 카테고리 정의
INPUT_PATHS = {
    "cyber_legacy": os.path.join(BASE_DIR, "online_pjh_json"),
    "subsidy": os.path.join(BASE_DIR, "subsidy_lsw_csv_json"),
    "funeral": os.path.join(BASE_DIR, "funeral_bsj_json"),
    "persona": os.path.join(BASE_DIR, "routine_chatbot"),
}

def read_file_safe(filepath):
    """파일을 여러 인코딩으로 시도하여 읽기"""
    encodings = ['utf-8', 'cp949', 'euc-kr']
    
    for enc in encodings:
        try:
            if filepath.endswith('.csv'):
                return pd.read_csv(filepath, encoding=enc)
            elif filepath.endswith('.json'):
                with open(filepath, 'r', encoding=enc) as f:
                    return json.load(f)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
        except Exception as e:
            logger.error(f"Error reading {filepath} with {enc}: {e}")
            return None
            
    logger.error(f"Failed to read {filepath} with all encodings.")
    return None

def process_csv_row(row):
    """CSV 행을 컨텍스트 문자열로 변환"""
    context_parts = []
    instruction = "상세 정보"
    
    for col, val in row.items():
        if pd.isna(val):
            continue
        
        val_str = str(val).strip()
        if not val_str:
            continue
            
        # 질문/제목 컬럼 찾기
        if col.lower() in ['질문', 'question', 'title', '제목', 'subject']:
            instruction = val_str
        
        context_parts.append(f"{col}: {val_str}")
        
    return instruction, "\n".join(context_parts)

def process_json_item(item):
    """JSON 항목을 컨텍스트 문자열로 변환"""
    context_parts = []
    instruction = "상세 정보"
    
    if isinstance(item, str):
        return "정보 요약", item
        
    for key, val in item.items():
        if val is None:
            continue
            
        val_str = str(val).strip()
        if not val_str:
            continue
            
        # 질문/제목 키 찾기
        if key.lower() in ['질문', 'question', 'title', '제목', 'subject', 'instruction']:
            instruction = val_str
            
        context_parts.append(f"{key}: {val_str}")
        
    return instruction, "\n".join(context_parts)

def main():
    merged_data = []
    seen_contexts = set()
    
    logger.info("Starting data integration...")
    
    for category, path in INPUT_PATHS.items():
        if not os.path.exists(path):
            logger.warning(f"Path not found: {path}. Skipping.")
            continue
            
        # CSV 및 JSON 파일 찾기
        files = glob.glob(os.path.join(path, "*.csv")) + glob.glob(os.path.join(path, "*.json"))
        logger.info(f"Found {len(files)} files in {category}")
        
        for filepath in files:
            filename = os.path.basename(filepath)
            logger.info(f"Processing {filename}...")
            
            data = read_file_safe(filepath)
            if data is None:
                continue
                
            items_to_process = []
            file_type = "unknown"
            
            if filepath.endswith('.csv'):
                file_type = "csv"
                # DataFrame을 딕셔너리 리스트로 변환
                items_to_process = [row for _, row in data.iterrows()]
            elif filepath.endswith('.json'):
                file_type = "json"
                if isinstance(data, list):
                    items_to_process = data
                elif isinstance(data, dict):
                    items_to_process = [data]
            
            for item in items_to_process:
                try:
                    if file_type == "csv":
                        instruction, context = process_csv_row(item)
                    else:
                        instruction, context = process_json_item(item)
                    
                    # 중복 제거 (특히 persona 카테고리)
                    if context in seen_contexts:
                        continue
                    
                    seen_contexts.add(context)
                    
                    entry = {
                        "instruction": instruction,
                        "context": context,
                        "metadata": {
                            "category": category,
                            "source_file": filename,
                            "file_type": file_type
                        }
                    }
                    merged_data.append(entry)
                    
                except Exception as e:
                    logger.error(f"Error processing item in {filename}: {e}")
                    continue

    # 결과 저장
    logger.info(f"Saving {len(merged_data)} items to {OUTPUT_FILE}...")
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            for entry in merged_data:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        logger.info("Data integration completed successfully.")
    except Exception as e:
        logger.error(f"Error saving output file: {e}")

if __name__ == "__main__":
    main()
