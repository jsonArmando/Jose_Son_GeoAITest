# app/core/ai_prompts.py - VERSIÓN OPTIMIZADA

# MÉTRICAS REDUCIDAS PARA TESTING - Expandir gradualmente
EXPECTED_OPERATIONAL_METRICS = [
    # Métricas más comunes en reportes de minería - VERIFICAR CON TUS IMÁGENES
    "Gold produced (oz)",
    "Gold sold (oz)", 
    "All-in sustaining costs ($/oz sold)",
    "Total cash costs ($/oz sold)",
]

EXPECTED_FINANCIAL_METRICS = [
    # Métricas financieras básicas - VERIFICAR CON TUS IMÁGENES  
    "Revenue",
    "Cost of sales", 
    "Adjusted EBITDA",
    "Net income (loss)",
    "Free cash flow",
    "Average realized gold price ($/oz)",
]

# Versión completa comentada para referencia
FULL_OPERATIONAL_METRICS = [
    "Gold produced (oz)", 
    "Gold sold (oz)",
    "Ore Mined - Open Pit (kt)",
    "Ore Mined - Underground (kt)", 
    "Total Ore Mined (kt)",
    "Waste Mined - Open Pit (kt)",
    "Strip Ratio - Open Pit (w:o)",
    "Gold Grade Mined - Open Pit (g/t)",
    "Gold Grade Mined - Underground (g/t)",
    "Ore Processed (kt)",
    "Ore Processed (tpd)",
    "Head Grade Processed (g/t Au)",
    "Gold Recovery (%)",
    "All-in sustaining costs ($/oz sold)",
    "Total cash costs ($/oz sold)",
]

FULL_FINANCIAL_METRICS = [
    "Revenue",
    "Cost of sales", 
    "Gross Profit",
    "Adjusted EBITDA",
    "EBITDA", 
    "Net income (loss)",
    "Earnings per share - basic ($)",
    "Earnings per share - diluted ($)",
    "Net cash generated from operating activities",
    "Free cash flow",
    "Capital Expenditures",
    "Total cash costs ($/oz sold)",
    "All-in sustaining costs ($/oz sold)",
    "Average realized gold price ($/oz)",
    "Media Luna Project capex",
]

def get_metric_extraction_prompt_optimized(pdf_text: str, report_name: str) -> str:
    """Versión optimizada del prompt con mejor manejo de longitud"""
    
    op_metrics_str = "\n- ".join(EXPECTED_OPERATIONAL_METRICS)
    fin_metrics_str = "\n- ".join(EXPECTED_FINANCIAL_METRICS)
    
    # Límite más conservador para evitar timeouts
    max_text_len = 500000  # Reducido de 700k
    
    if len(pdf_text) > max_text_len:
        print(f"AI Prompts: Truncando texto de {len(pdf_text)} a {max_text_len} caracteres")
        # Intentar mantener las primeras páginas que suelen tener los datos financieros
        truncated_text = pdf_text[:max_text_len]
    else:
        truncated_text = pdf_text

    prompt = f"""You are an expert financial analyst specializing in mining company reports, specifically Torex Gold.
Report name: "{report_name}"

Extract key metrics from this financial report text:
--- PDF TEXT START ---
{truncated_text}
--- PDF TEXT END ---

CRITICAL INSTRUCTIONS:
1. PERIOD IDENTIFICATION: Determine the YEAR (YYYY) and QUARTER (Q1, Q2, Q3, Q4, or FY) from the report
2. EXACT METRIC NAMES: Find metrics with the EXACT names listed below
3. VALUES: Extract numerical values. For millions (M$), thousands (k), note the unit. For $/oz, use as-is
4. MISSING DATA: Use "Not found" if a metric or value is not found. DO NOT invent values
5. UNITS: If metric includes unit (e.g. "Revenue (M$)"), value should match that unit

**OPERATIONAL METRICS** (quarterly and YTD values):
- {op_metrics_str}

**FINANCIAL METRICS** (quarterly and YTD values):  
- {fin_metrics_str}

**REQUIRED JSON OUTPUT FORMAT:**
```json
{{
  "report_details_inferred": {{
    "year": "YYYY or Not found",
    "quarter": "Q1|Q2|Q3|Q4|FY or Not found"
  }},
  "operational_highlights": [
    {{"metric_name": "Gold produced (oz)", "quarter_value": "VALUE or Not found", "ytd_value": "VALUE or Not found"}}
    // Include ALL operational metrics listed above
  ],
  "financial_highlights": [
    {{"metric_name": "Revenue", "quarter_value": "VALUE or Not found", "ytd_value": "VALUE or Not found"}}
    // Include ALL financial metrics listed above
  ],
  "llm_extraction_notes": "Important observations or difficulties during extraction"
}}
```

IMPORTANT: 
- For Q1: quarter_value and ytd_value are usually the same
- For Q2: ytd_value is Q1+Q2 cumulative  
- For Q3: ytd_value is Q1+Q2+Q3 cumulative
- For Q4: quarter_value is Q4 only, ytd_value is full year
- For Annual (FY): both values should be the same annual figure
- Include ALL metrics from both lists, use "Not found" where needed"""

    return prompt

def get_simple_test_prompt() -> str:
    """Prompt simple para testing de conectividad"""
    return '''Respond with this exact JSON format:
{
  "test": "successful",
  "message": "Hello from Gemini",
  "timestamp": "2024"
}'''

def get_pdf_structure_extraction_prompt(pdf_text_content: str) -> str:
    """Versión simplificada para análisis estructural"""
    max_len = 200000  # Más conservador
    truncated_text = pdf_text_content[:max_len] if len(pdf_text_content) > max_len else pdf_text_content

    return f"""Analyze this financial report and identify key information:

--- PDF TEXT ---
{truncated_text}
--- END PDF TEXT ---

Return JSON with:
1. Report period (year and quarter)
2. Key financial tables found
3. Production/operational data sections

Format:
{{
  "report_period": {{"year": "YYYY", "quarter": "QX"}},
  "tables_found": ["table names"],
  "sections_found": ["section names"]
}}"""

# Función para cambiar entre versión reducida y completa
def use_full_metrics():
    """Cambiar a métricas completas (usar solo si la versión reducida funciona)"""
    global EXPECTED_OPERATIONAL_METRICS, EXPECTED_FINANCIAL_METRICS
    EXPECTED_OPERATIONAL_METRICS = FULL_OPERATIONAL_METRICS.copy()
    EXPECTED_FINANCIAL_METRICS = FULL_FINANCIAL_METRICS.copy()
    print("✅ Cambiado a métricas completas")

def use_minimal_metrics():
    """Usar métricas mínimas para testing"""
    global EXPECTED_OPERATIONAL_METRICS, EXPECTED_FINANCIAL_METRICS
    EXPECTED_OPERATIONAL_METRICS = ["Gold produced (oz)", "Gold sold (oz)"]
    EXPECTED_FINANCIAL_METRICS = ["Revenue", "Net income (loss)"]
    print("✅ Cambiado a métricas mínimas")

# Función principal - usar la optimizada por defecto
def get_metric_extraction_prompt(pdf_text: str, report_name: str) -> str:
    return get_metric_extraction_prompt_optimized(pdf_text, report_name)