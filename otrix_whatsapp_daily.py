#!/usr/bin/env python3
import json
from datetime import datetime
from pathlib import Path
CONTEXT_SUMMARY_PATH = "/home/diego/otrix_contexto_cron_minimo.md"
OUTPUT_DIR = Path("/home/diego/.hermes/cron/output/fb2f35670b85")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
output_file = OUTPUT_DIR / f"{timestamp}.md"
try:
    with open(CONTEXT_SUMMARY_PATH, "r", encoding="utf-8") as f:
        context = f.read().strip()
except:
    context = "Error cargando contexto"
timestamp_now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
report = f"# Reporte OTRIX - {timestamp_now}\n\n{context}\n\nGenerado por Hermes Cron"
output_file.write_text(report, encoding="utf-8")
print(json.dumps({"status": "success", "output_file": str(output_file)}, ensure_ascii=False))
