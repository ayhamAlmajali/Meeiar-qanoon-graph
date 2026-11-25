from pathlib import Path

p = Path("backend/graph_engine.py")
src = p.read_text(encoding="utf-8")

old_block = """        matching_articles = [
            a for a in self.articles
            if str(a.get("legislation_title") or "").strip() == selected
        ]"""

new_block = """        matching_articles = [
            a for a in self.articles
            if str(a.get("legislation_title") or "").strip() == selected
            and a.get("searchable", True) is not False
            and a.get("quality_status") != "corrupted_ocr"
        ]"""

assert old_block in src, "Target block not found in graph_engine.py"
p.write_text(src.replace(old_block, new_block, 1), encoding="utf-8")
print("Updated timeline_evolution to exclude corrupted OCR articles.")
