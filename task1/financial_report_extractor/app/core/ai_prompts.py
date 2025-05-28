# app/core/ai_prompts.py

# !!! IMPORTANTE: Revisa y ajusta estas listas para que coincidan EXACTAMENTE
# con los nombres de las métricas de las tablas que quieres construir,
# según las imágenes proporcionadas en el test. !!!

EXPECTED_OPERATIONAL_METRICS = [
    "Gold produced (oz)", # Ejemplo
    "Gold sold (oz)",     # Ejemplo
    "Ore mined (kt) - ELG Open Pit", # Ejemplo si quieres desglosar así
    "Ore mined (tpd) - ELG Open Pit", # Ejemplo
    "Waste mined (kt) - ELG Open Pit", # Ejemplo
    "Strip ratio (waste:ore) - ELG Open Pit", # Ejemplo
    "Gold grade (gpt) - ELG Open Pit", # Ejemplo
    "Ore mined (kt) - ELG Underground", # Ejemplo
    "Ore mined (tpd) - ELG Underground", # Ejemplo
    "Gold grade (gpt) - ELG Underground", # Ejemplo
    "Ore processed (kt)", # Ejemplo
    "Ore processed (tpd)", # Ejemplo
    "Gold grade (gpt) - Processing", # Ejemplo
    "Gold recovery (%)", # Ejemplo
    # Añade aquí TODAS las métricas operativas de tu tabla objetivo
]

EXPECTED_FINANCIAL_METRICS = [
    "Revenue (M$)", # Ejemplo, considera si incluyes la unidad en el nombre esperado
    "Cost of sales (M$)", # Ejemplo
    "Gross profit (M$)", # Ejemplo
    "Adjusted EBITDA (M$)", # Ejemplo
    "Net income (loss) (M$)", # Ejemplo
    "Earnings (loss) per share - basic ($)", # Ejemplo
    "Net cash generated from operating activities (M$)", # Ejemplo
    "Free cash flow (M$)", # Ejemplo
    "Media Luna Project capex (M$)", # Ejemplo
    "Total cash costs ($/oz)", # Ejemplo
    "All-in sustaining costs ($/oz)", # Ejemplo
    "Average realized gold price ($/oz)", # Ejemplo
    # Añade aquí TODAS las métricas financieras de tu tabla objetivo
]


def get_pdf_structure_extraction_prompt(pdf_text_content: str) -> str:
    # Este prompt es opcional si el de extracción de métricas funciona bien con texto crudo.
    # Podría usarse para un pre-procesamiento si la extracción directa es difícil.
    # Por ahora, nos enfocamos en el prompt de extracción de métricas.
    prompt = f"""
Eres un asistente de IA especializado en analizar documentos PDF financieros.
El siguiente es el contenido de texto extraído de un informe financiero:
--- BEGIN PDF TEXT CONTENT ---
{pdf_text_content[:200000]} 
--- END PDF TEXT CONTENT ---

Tu tarea es analizar este texto e identificar secciones clave y tablas que contengan datos financieros u operativos.
Extrae el año y el trimestre (Q1, Q2, Q3, Q4) o si es un informe Anual (FY).
Formatea las tablas que encuentres como listas de listas o un JSON estructurado.
Devuelve tu análisis en formato JSON. Ejemplo:
{{
  "report_period_info": {{ "year": YYYY, "quarter": "QX | FY", "text_found": "Texto original del periodo" }},
  "extracted_tables": [ {{ "table_name_guess": "Nombre tabla", "data_csv": "col1,col2\\nval1,val2" }} ],
  "relevant_text_sections": ["Texto relevante..."]
}}
Si no puedes identificar alguna parte, usa "Not found" o un array/objeto vacío.
"""
    return prompt

def get_metric_extraction_prompt(structured_pdf_data_or_raw_text: str, report_name: str) -> str:
    op_metrics_str = "\n- ".join(EXPECTED_OPERATIONAL_METRICS)
    fin_metrics_str = "\n- ".join(EXPECTED_FINANCIAL_METRICS)

    prompt = f"""
Eres un analista financiero experto en extraer métricas clave de informes financieros de empresas mineras, específicamente Torex Gold.
El nombre del informe que estás analizando es: "{report_name}"

A partir del siguiente texto extraído de un informe financiero en PDF (puede ser texto crudo o datos pre-estructurados):
--- BEGIN PDF DATA ---
{structured_pdf_data_or_raw_text[:200000]} 
--- END PDF DATA ---

Tu tarea principal es extraer las siguientes métricas para construir dos tablas: "Operational Highlights" y "Financial Highlights".
Para cada métrica, debes encontrar el valor correspondiente al **trimestre actual** (ej. "Three months ended [Date]", "Q1 2023") Y el valor **acumulado del año hasta la fecha** (YTD, ej. "Six months ended [Date]", "Year ended [Date]", "Full Year").

**Instrucciones Cruciales:**
1.  **Identificación del Periodo:** Primero, determina el **año** y el **trimestre** (Q1, Q2, Q3, Q4) o si es un informe **Anual (FY)** al que se refiere el documento. Incluye esto en `report_details_inferred`.
2.  **Nombres de Métricas:** Busca las métricas EXACTAMENTE como se listan abajo. Si una métrica en el documento tiene un nombre ligeramente diferente pero significa lo mismo, mapeala al nombre de la lista.
3.  **Valores Numéricos:** Extrae los valores numéricos. Si los números están expresados en miles (ej. "USD in thousands", "000s"), convierte al valor completo (ej. 500 thousands -> 500000). Si están en millones (M$), indícalo o convierte (ej. 10.5M -> 10500000). Si no puedes convertir, mantén el valor como está pero anota la unidad (ej. "10.5 (Millions USD)"). Para costos por onza ($/oz), el valor ya está en la unidad correcta.
4.  **Datos Faltantes:** Si una métrica específica o uno de sus valores (trimestral o YTD) no se encuentra en el documento o no se puede determinar con certeza, devuelve el string "Not found" para ese valor específico. NO INVENTES VALORES.
5.  **Unidades:** Presta atención a las unidades (ej. oz, $, t, g/t, M$, koz). Si el nombre de la métrica en la lista ya incluye la unidad (ej. "Revenue (M$)"), asegúrate que el valor corresponda a esa unidad. Si la métrica es solo "Revenue", el valor debe ser el número completo.

**Tabla 1: Operational Highlights**
Métricas a extraer (busca el valor trimestral y YTD para cada una):
- {op_metrics_str}

**Tabla 2: Financial Highlights**
Métricas a extraer (busca el valor trimestral y YTD para cada una):
- {fin_metrics_str}

**Formato de Salida Obligatorio (JSON VÁLIDO):**
Devuelve la información ÚNICAMENTE en el siguiente formato JSON. No incluyas explicaciones adicionales fuera de este JSON.
{{
  "report_details_inferred": {{
    "year": "YYYY | Not found", 
    "quarter": "Q1 | Q2 | Q3 | Q4 | FY | Not found"
  }},
  "operational_highlights": [
    // Para cada métrica en EXPECTED_OPERATIONAL_METRICS:
    {{ "metric_name": "Nombre de la métrica operativa de la lista", "quarter_value": "VALOR_TRIMESTRAL | Not found", "ytd_value": "VALOR_YTD | Not found" }}
    // ... más métricas operativas
  ],
  "financial_highlights": [
    // Para cada métrica en EXPECTED_FINANCIAL_METRICS:
    {{ "metric_name": "Nombre de la métrica financiera de la lista", "quarter_value": "VALOR_TRIMESTRAL | Not found", "ytd_value": "VALOR_YTD | Not found" }}
    // ... más métricas financieras
  ],
  "llm_extraction_notes": "Cualquier observación, suposición importante o dificultad encontrada durante la extracción (ej. cómo manejaste 'USD in thousands', si una métrica fue difícil de encontrar, o si el documento parecía ser de un periodo diferente al esperado)."
}}

Asegúrate de que la salida sea un JSON válido. Incluye TODAS las métricas solicitadas en las listas `operational_highlights` y `financial_highlights`, usando "Not found" si es necesario para los valores.
El campo `report_details_inferred` es tu mejor estimación del periodo del informe basado en el contenido.
Si el informe es claramente Anual (FY), el `quarter_value` y el `ytd_value` deberían ser el mismo (el valor anual).
Si el informe es un Q4 que también resume el año completo, el `quarter_value` es para Q4 y el `ytd_value` es para el año completo.
"""
    # Truncar el prompt si es demasiado largo para asegurar que la solicitud no falle por tamaño
    # Aunque Gemini 1.5 Flash tiene un contexto grande, los prompts muy largos pueden ser problemáticos.
    # La parte más variable es structured_pdf_data_or_raw_text.
    # El resto del prompt es fijo.
    prompt_template_len = len(prompt) - len(structured_pdf_data_or_raw_text)
    max_text_len = 3000000 - prompt_template_len - 1000 # Dejar margen; Gemini 1.5 Flash es 1M tokens, ~4M chars
                                                       # Reducido a 3M chars para ser más conservador con el prompt total.
    
    if len(structured_pdf_data_or_raw_text) > max_text_len:
        print(f"AI Prompts: Texto del PDF truncado de {len(structured_pdf_data_or_raw_text)} a {max_text_len} caracteres para el prompt.")
        truncated_text = structured_pdf_data_or_raw_text[:max_text_len]
        # Reconstruir el prompt con el texto truncado
        prompt = prompt.replace(structured_pdf_data_or_raw_text, truncated_text)

    return prompt
