# app/core/ai_prompts.py

# Estos prompts son ejemplos y necesitarán ser refinados y probados.
# La efectividad de la extracción dependerá en gran medida de la calidad de estos prompts.

# Lista de métricas objetivo basada en la imagen proporcionada en el README del test.
# Es crucial que estos nombres coincidan con lo que se espera en las tablas.
# Se pueden añadir más o ajustar según sea necesario.
EXPECTED_OPERATIONAL_METRICS = [
    "Gold produced (oz)",
    "Gold sold (oz)",
    "Average realized gold price ($/oz)",
    "Total cash cost ($/oz sold)", # Puede que no siempre esté como "Total"
    "All-in sustaining cost (AISC) ($/oz sold)" # Puede que no siempre esté como "Total"
    # Añadir más si se identifican en la imagen o son relevantes
    # "Underground production ore (tonnes milled)",
    # "Underground grade (g/t milled)",
    # "Processing plant recovery (%)"
]

EXPECTED_FINANCIAL_METRICS = [
    "Revenue",
    "Cost of sales", # A veces "Cost of goods sold"
    "Gross profit", # O "Gross margin"
    "Adjusted EBITDA", # A veces solo "EBITDA"
    "Income (loss) from mine operations",
    "Net income (loss)", # O "Profit (loss) for the period"
    "Earnings (loss) per share - basic", # EPS
    "Earnings (loss) per share - diluted",
    "Cash flow from (used in) operating activities", # O variaciones
    "Capital expenditures", # Capex
    # Añadir más si se identifican en la imagen o son relevantes
    # "Exploration and evaluation expenditures",
    # "Cash and cash equivalents",
    # "Total debt"
]


def get_pdf_structure_extraction_prompt(pdf_text_content: str) -> str:
    """
    Prompt para un LLM (Gemini) para extraer estructura y contenido de un PDF.
    Asume que pdf_text_content es el texto crudo extraído de un PDF.
    """
    # Se podría mejorar este prompt para pedir al LLM que identifique encabezados,
    # párrafos, y especialmente tablas con sus filas y columnas.
    # Para simplificar, inicialmente podríamos solo pasar el texto y pedir que el
    # siguiente LLM (extractor de métricas) trabaje sobre el texto plano.
    # Sin embargo, una extracción estructurada aquí ayudaría mucho al siguiente paso.

    prompt = f"""
Eres un asistente de IA experto en analizar documentos PDF financieros.
El siguiente es el contenido de texto extraído de un informe financiero:
--- BEGIN PDF TEXT CONTENT ---
{pdf_text_content}
--- END PDF TEXT CONTENT ---

Tu tarea es analizar este texto y prepararlo para una extracción de métricas financieras.
Por favor, intenta identificar y estructurar la información de la siguiente manera:
1.  **Identificación del Periodo del Informe:** Busca frases que indiquen el periodo del informe (ej. "Three months ended March 31, 2023", "Year ended December 31, 2022"). Extrae el año y el trimestre (Q1, Q2, Q3, Q4) o si es un informe Anual (FY).
2.  **Extracción de Tablas Clave:** Identifica cualquier tabla que parezca contener datos financieros u operativos. Si puedes, formatea cada tabla como una lista de listas (representando filas y celdas) o un JSON estructurado. Presta especial atención a las tablas tituladas "Consolidated Statements of Operations", "Consolidated Balance Sheets", "Consolidated Statements of Cash Flows", "Operational Highlights", "Financial Highlights", o similares.
3.  **Texto Relevante:** Extrae bloques de texto que parezcan discutir resultados financieros, producción, ventas, costos, o proyecciones.

Devuelve tu análisis en formato JSON. Ejemplo de la estructura deseada:
{{
  "report_period_info": {{
    "year": YYYY,
    "quarter": "QX | FY | Not found",
    "period_description_found": "Texto original del periodo encontrado en el documento"
  }},
  "extracted_tables": [
    {{
      "table_name_guess": "Nombre estimado de la tabla (ej: Financial Highlights)",
      "table_data_csv_like": "COL1_HEADER,COL2_HEADER\\nROW1_VAL1,ROW1_VAL2\\nROW2_VAL1,ROW2_VAL2"
      // Opcionalmente: "table_data_json": [ { "COL1_HEADER": "ROW1_VAL1", ... } ]
    }}
    // ... más tablas
  ],
  "relevant_text_sections": [
    "Texto relevante sección 1...",
    "Texto relevante sección 2..."
  ]
}}

Si no puedes identificar alguna parte, usa "Not found" o un array/objeto vacío según corresponda.
Prioriza la precisión. No inventes información.
"""
    return prompt

def get_metric_extraction_prompt(structured_pdf_data: str, report_name: str) -> str:
    """
    Prompt para el LLM (Gemini) para extraer métricas específicas de los datos estructurados del PDF.
    structured_pdf_data es el JSON devuelto por el LLM anterior.
    """
    # Convertir listas de métricas a strings para el prompt
    op_metrics_str = "\n- ".join(EXPECTED_OPERATIONAL_METRICS)
    fin_metrics_str = "\n- ".join(EXPECTED_FINANCIAL_METRICS)

    prompt = f"""
Eres un analista financiero experto en extraer métricas clave de informes financieros de empresas mineras, específicamente Torex Gold.
El nombre del informe que estás analizando es: "{report_name}"

A partir de los siguientes datos, que han sido pre-procesados de un informe financiero en PDF:
--- BEGIN PRE-PROCESSED PDF DATA (JSON) ---
{structured_pdf_data}
--- END PRE-PROCESSED PDF DATA (JSON) ---

Tu tarea es extraer las siguientes métricas para construir dos tablas: "Operational Highlights" y "Financial Highlights".
Para cada métrica, busca el valor correspondiente al **trimestre actual** (ej. "Three months ended [Date]") Y el valor **acumulado del año hasta la fecha** (YTD, ej. "Six months ended [Date]", "Nine months ended [Date]", "Year ended [Date]").

**Instrucciones Importantes:**
1.  **Identificación del Periodo:** Usa la información en `report_period_info` del JSON de entrada, o infiérelo del contexto si es necesario, para determinar el año y el trimestre (Q1, Q2, Q3, Q4) o si es un informe Anual (FY). Si el informe es anual (FY), el valor "trimestral" y "YTD" serán el mismo (el valor anual).
2.  **Valores Numéricos:** Intenta extraer los valores numéricos. Si los números están en miles o millones (ej. "USD in thousands"), anota esto o, idealmente, convierte al valor completo (ej. 500 thousands -> 500000). Si no es posible la conversión, mantén el valor como está pero indica la unidad si es clara (ej. "500 (thousands USD)").
3.  **Datos Faltantes:** Si una métrica específica no se encuentra en el documento o no se puede determinar con certeza, devuelve el string "Not found" para ese valor. NO INVENTES VALORES.
4.  **Unidades:** Presta atención a las unidades (ej. oz, $, t, g/t). Si es posible, inclúyelas o asegúrate de que el contexto sea claro. Para precios y costos por onza, el valor ya debería estar en $/oz.
5.  **Variaciones de Nombres:** Las métricas pueden tener nombres ligeramente diferentes en los informes. Usa tu juicio para mapearlas a las métricas solicitadas. Por ejemplo, "Profit for the period" es "Net income". "All-in sustaining costs" es "AISC".

**Tabla 1: Operational Highlights**
Métricas a extraer (busca el valor trimestral y YTD para cada una):
- {op_metrics_str}

**Tabla 2: Financial Highlights**
Métricas a extraer (busca el valor trimestral y YTD para cada una):
- {fin_metrics_str}

**Formato de Salida Obligatorio (JSON):**
Devuelve la información ÚNICAMENTE en el siguiente formato JSON. No incluyas explicaciones adicionales fuera de este JSON.
{{
  "report_details_inferred": {{
    "year": YYYY, // Año inferido del informe
    "quarter": "QX | FY" // Trimestre (Q1, Q2, Q3, Q4) o Año Completo (FY) inferido
  }},
  "operational_highlights": [
    {{ "metric_name": "Nombre de la métrica operativa", "quarter_value": "VALOR_TRIMESTRAL | Not found", "ytd_value": "VALOR_YTD | Not found" }},
    // ... todas las métricas operativas solicitadas
  ],
  "financial_highlights": [
    {{ "metric_name": "Nombre de la métrica financiera", "quarter_value": "VALOR_TRIMESTRAL | Not found", "ytd_value": "VALOR_YTD | Not found" }},
    // ... todas las métricas financieras solicitadas
  ],
  "llm_extraction_notes": "Cualquier nota o suposición importante que hiciste durante la extracción (ej. cómo manejaste 'USD in thousands', o si una métrica fue difícil de encontrar)."
}}

Asegúrate de que la salida sea un JSON válido. Incluye TODAS las métricas solicitadas en las listas, usando "Not found" si es necesario.
El campo `report_details_inferred` es tu mejor estimación del periodo del informe basado en el contenido.
"""
    return prompt

# Podríamos añadir más prompts, por ejemplo, uno para validar la salida del LLM
# o para calcular el score de precisión si quisiéramos que el LLM participara en eso.
