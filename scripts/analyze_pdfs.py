import fitz
from pathlib import Path

def analyze_pdf(filename):
    path = Path(filename)
    if not path.exists():
        print(f"File not found: {filename}")
        return

    doc = fitz.open(path)
    print(f"\nAnalyzing: {filename}")
    print(f"Total Pages: {len(doc)}")
    
    total_text_len = 0
    total_images = 0
    
    for i, page in enumerate(doc):
        text = page.get_text()
        images = page.get_images()
        
        total_text_len += len(text)
        total_images += len(images)
        
        if i < 3:  # Print details for first 3 pages only
            print(f"  Page {i+1}: Text Length={len(text)}, Images={len(images)}")
            if len(text) < 100 and len(images) > 0:
                print(f"    [WARNING] Low text count on page {i+1} with images. Potential OCR candidate.")

    print(f"Summary: Avg Text/Page={total_text_len/len(doc):.1f}, Total Images={total_images}")

files = [
    "2. 국세청-상속·증여 세금상식1.pdf",
    "3. 국세청-상속·증여 세금상식Ⅱ.pdf"
]

base_dir = Path("/Users/souluk/SKN_19/SKN_19_STUDY/well_dying/legacy_data_raw")

for f in files:
    analyze_pdf(base_dir / f)
