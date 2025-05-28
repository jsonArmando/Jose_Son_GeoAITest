import React, { useState, useEffect, useCallback } from 'react';

// --- Iconos SVG (sus colores se adaptarán al contexto o se definirán explícitamente si es necesario) ---
const IconLoader = ({ className = "h-6 w-6" }) => (
  <svg className={`animate-spin text-blue-600 ${className}`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
  </svg>
);
const IconCheckCircle = ({ className = "w-6 h-6" }) => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={`${className} text-green-600`}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
  </svg>
);
const IconExclamationTriangle = ({ className = "w-6 h-6" }) => (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={`${className} text-yellow-600`}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
    </svg>
);
const IconInformationCircle = ({ className = "w-6 h-6" }) => (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={`${className} text-blue-600`}>
        <path strokeLinecap="round" strokeLinejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z" />
    </svg>
);
const IconDocumentChartBar = ({ className = "w-7 h-7" }) => ( // Ajustado tamaño
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={className}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 0 1-1.125-1.125M3.375 19.5V7.5M17.625 7.5l-4.5-4.5m0 0L8.625 7.5M13.125 3v4.5A2.25 2.25 0 0 0 15.375 9.75h4.5M3.375 21.75A2.25 2.25 0 0 0 5.625 24h12.75c1.243 0 2.25-1.007 2.25-2.25V11.25c0-1.243-.934-2.354-2.13-2.531M3.375 21.75V13.125M3.375 13.125V4.875c0-.621.504-1.125 1.125-1.125H9M15 9.75H9.375M15 13.125H9.375M15 16.5H9.375M13.125 21.75v-4.5c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21.75" />
    </svg>
);
const IconPhoto = ({ className = "w-7 h-7" }) => ( 
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={className}>
        <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 6v12a1.5 1.5 0 0 0 1.5 1.5Zm10.5-11.25h.008v.008h-.008V8.25Zm.158 0a.225.225 0 1 1-.45 0 .225.225 0 0 1 .45 0Z" />
    </svg>
);
const IconMapPin = ({ className = "w-7 h-7" }) => ( 
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={className}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z" />
    </svg>
);
const IconLink = ({ className = "w-5 h-5" }) => (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={className}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
    </svg>
);
const IconListBullet = ({ className = "w-5 h-5" }) => (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={className}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 6.75h7.5M8.25 12h7.5m-7.5 5.25h7.5M3.75 6.75h.007v.008H3.75V6.75Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0ZM3.75 12h.007v.008H3.75V12Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm-.375 5.25h.007v.008H3.75v-.008Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" />
    </svg>
);
const IconTableCells = ({ className = "w-5 h-5" }) => (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={className}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h12A2.25 2.25 0 0 1 20.25 6v12A2.25 2.25 0 0 1 18 20.25H6A2.25 2.25 0 0 1 3.75 18V6ZM3.75 12h16.5M12 3.75v16.5" />
    </svg>
);
const IconWrenchScrewdriver = ({ className = "w-5 h-5" }) => ( 
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={className}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.475-2.475a1.125 1.125 0 0 1 1.591 1.591l-2.475 2.475M11.42 15.17l-4.636-4.636a1.125 1.125 0 0 1 0-1.591l.943-.943a1.125 1.125 0 0 1 1.591 0L11.42 15.17ZM3 21l5.877-5.877M11.42 15.17l.471-1.717L5.877 5.877l-1.717.471L3 21Z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M12.228 12.228 15 9.456l-2.475-2.475a1.125 1.125 0 0 0-1.591 1.591L12.228 12.228Z" />
    </svg>
);
const IconShieldCheck = ({ className = "w-5 h-5" }) => ( 
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={className}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 0 1-1.043 3.296 3.745 3.745 0 0 1-3.296 1.043A3.745 3.745 0 0 1 12 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 0 1-3.296-1.043 3.745 3.745 0 0 1-1.043-3.296A3.745 3.745 0 0 1 3 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 0 1 1.043-3.296 3.746 3.746 0 0 1 3.296-1.043A3.746 3.746 0 0 1 12 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 0 1 3.296 1.043 3.746 3.746 0 0 1 1.043 3.296A3.745 3.745 0 0 1 21 12Z" />
    </svg>
);

// --- Constantes y Configuración ---
const API_BASE_URL = 'http://localhost:8000/api/v1'; 
const APP_TITLE = "GeoAI Technical Test Dashboard";

// --- Componentes de UI Reutilizables ---
const MainCard = ({ title, children, icon, className = "" }) => (
    <div className={`bg-white border border-slate-200 p-6 rounded-xl shadow-lg ${className}`}>
        {title && (
            <div className="flex items-center text-blue-700 mb-6 border-b-2 border-blue-200 pb-4">
                {icon && <span className="mr-3 text-blue-600">{icon}</span>}
                <h2 className="text-xl sm:text-2xl font-semibold">{title}</h2> {/* Título más pequeño */}
            </div>
        )}
        {children}
    </div>
);

const SubCard = ({ title, children, className = "" }) => (
    <div className={`bg-slate-50 border border-slate-300 p-5 rounded-lg shadow-md ${className}`}>
        {title && <h3 className="text-lg font-semibold text-blue-700 mb-4 border-b border-slate-200 pb-2">{title}</h3>} {/* Título más pequeño */}
        {children}
    </div>
);

const SubTabButton = ({ label, isActive, onClick, icon }) => (
    <button
        onClick={onClick}
        className={`flex items-center space-x-2 px-4 py-2.5 text-xs sm:text-sm font-medium rounded-md transition-colors duration-150 border
                    ${isActive 
                        ? 'bg-blue-600 text-white border-blue-700 shadow-md' 
                        : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-100 hover:text-blue-700 hover:border-blue-400'}`}
    >
        {icon && React.cloneElement(icon, { className: `w-4 h-4 ${isActive ? 'text-white' : 'text-blue-600'}` })}
        <span>{label}</span>
    </button>
);

const MetricDisplay = ({ label, value, valueColor = "text-slate-700", unit = "", size="normal" }) => (
    <div className={`bg-slate-100 border border-slate-200 p-4 rounded-lg shadow-sm ${size === 'small' ? 'text-sm' : ''}`}>
        <p className={`text-slate-500 ${size === 'small' ? 'text-xs mb-0.5' : 'text-sm mb-1'}`}>{label}</p>
        <p className={`font-bold ${valueColor} ${size === 'small' ? 'text-lg' : 'text-2xl'}`}>
            {value !== undefined && value !== null ? value : <span className="italic text-slate-400">N/A</span>}
            {unit && value !== undefined && value !== null && <span className={`font-normal text-slate-500 ${size === 'small' ? 'text-xs ml-1' : 'text-sm ml-1.5'}`}>{unit}</span>}
        </p>
    </div>
);

// --- Tarea 1: Sub-Componentes por Punto ---
const Point1WebsiteInfo = () => (
    <SubCard title="Punto 1: Sitio Web Objetivo">
        <p className="text-slate-700 mb-2">El proceso de extracción se enfoca en el siguiente sitio web para obtener los informes financieros:</p>
        <div className="bg-slate-200 border border-slate-300 p-3 rounded-md">
            <a 
                href="https://torexgold.com/investors/financial-reports/" 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-blue-600 hover:text-blue-700 hover:underline font-mono break-all text-sm"
            >
                https://torexgold.com/investors/financial-reports/
            </a>
        </div>
        <p className="text-slate-500 mt-3 text-xs italic">Este punto se cumple accediendo programáticamente a la URL mencionada para el web scraping, utilizando el adaptador `report_fetcher_adapter.py`.</p>
    </SubCard>
);

const Point2FetchProcess = ({ fetchInfo, onTriggerExtraction, isExtracting, extractionMessage }) => (
    <SubCard title="Punto 2: Obtención de Informes (2021-2024)">
        <div className="space-y-5">
            <MetricDisplay label="Rango de Años Configurado" value={fetchInfo.yearRange} valueColor="text-blue-700" />
            <MetricDisplay label="Informes Identificados (última ejecución)" value={fetchInfo.reportsIdentified} valueColor="text-blue-700"/>
            <MetricDisplay label="Estado del Proceso de Extracción" value={fetchInfo.status} valueColor={fetchInfo.status.includes("iniciado") || fetchInfo.status.includes("Procesando") ? "text-yellow-600" : "text-green-600"}/>
            <button
                onClick={onTriggerExtraction}
                disabled={isExtracting}
                className="mt-4 w-full sm:w-auto bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-8 rounded-lg shadow-md hover:shadow-lg transition duration-150 ease-in-out transform hover:scale-105 focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:opacity-60 flex items-center justify-center"
            >
                {isExtracting && <IconLoader className="inline mr-2 h-5 w-5 text-white"/>}
                {isExtracting ? 'Extrayendo Informes...' : 'Disparar Nueva Búsqueda y Extracción'}
            </button>
            {extractionMessage && (
                <div className={`mt-3 p-3 rounded-md text-sm ${extractionMessage.type === 'error' ? 'bg-red-100 text-red-700 border border-red-300' : extractionMessage.type === 'success' ? 'bg-green-100 text-green-700 border border-green-300' : 'bg-blue-100 text-blue-700 border border-blue-300'}`}>
                    <div className="flex items-center">
                        {extractionMessage.type === 'error' ? <IconExclamationTriangle className="w-5 h-5 mr-2 text-red-600"/> : extractionMessage.type === 'success' ? <IconCheckCircle className="w-5 h-5 mr-2 text-green-600"/> : <IconInformationCircle className="w-5 h-5 mr-2 text-blue-600"/>}
                        <span>{extractionMessage.text}</span>
                    </div>
                </div>
            )}
            <p className="text-slate-500 mt-3 text-xs italic">El backend (`report_fetcher_adapter.py`) escanea el sitio, filtra por los años 2021-2024 y selecciona PDFs relevantes (MD&A, FS, Presentaciones) según la lógica de priorización implementada.</p>
        </div>
    </SubCard>
);

const Point3MetricTables = ({ annualTableData, selectedYear, onYearChange, years, isLoading, error }) => {
    const renderTable = (title, data, tableType) => (
        <div className="mt-8">
          <h4 className="text-lg font-semibold text-blue-700 mb-4">{title}</h4>
          {data && data.length > 0 ? (
            <div className="overflow-x-auto custom-scrollbar bg-white border border-slate-300 p-4 rounded-lg shadow-md">
              <table className="w-full min-w-[800px] text-sm">
                <thead className="text-slate-600 uppercase bg-slate-100">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold sticky left-0 bg-slate-100 z-10 min-w-[220px] max-w-[320px] rounded-tl-md">Métrica</th>
                    {["Q1", "Q2", "Q3", "Q4", "Anual"].map(q => (
                      <th key={q} className="px-4 py-3 text-right font-semibold min-w-[90px]">{q}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="text-slate-700">
                  {data.map((row, index) => (
                    <tr key={`${tableType}-${index}-${row.metric_name}`} className="border-t border-slate-200 hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 font-medium text-slate-800 whitespace-normal break-words sticky left-0 bg-white hover:bg-slate-50 z-10 min-w-[220px] max-w-[320px]">{row.metric_name}</td>
                      {[row.q1_value, row.q2_value, row.q3_value, row.q4_value, row.annual_value].map((val, i) => (
                        <td key={i} className={`px-4 py-3 text-right whitespace-nowrap ${val === 'Not found' || val === null || val === '' ? 'text-slate-400 italic' : (i === 4 ? 'font-bold text-blue-700' : 'text-green-700')}`}>
                          {val === null || val === '' ? 'N/A' : val}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-6 px-4 bg-slate-100 border border-slate-200 rounded-md">
                <IconExclamationTriangle className="mx-auto h-10 w-10 text-yellow-500 mb-3"/>
                <p className="text-slate-600">No hay datos disponibles para esta tabla.</p>
                <p className="text-xs text-slate-400 mt-1">Asegúrate de que la extracción se haya completado para el año {selectedYear} y que el backend pueda consolidar los datos.</p>
            </div>
          )}
        </div>
      );

    return (
        <SubCard title="Punto 3: Métricas Extraídas (Tablas Consolidadas Anuales)">
            <p className="text-slate-600 mb-5 text-sm">
                Visualización de las tablas "Operational Highlights" y "Financial Highlights" consolidadas por año. 
                Estos datos se obtienen del endpoint <code className="bg-slate-200 text-xs px-1.5 py-1 rounded text-blue-700 font-mono">/api/v1/reports/annual-table/{'{year}'}</code>, 
                que agrega la información extraída por la IA de los informes individuales.
            </p>
            <div className="flex flex-col sm:flex-row items-center space-y-3 sm:space-y-0 sm:space-x-4 mb-6 p-4 bg-slate-100 border border-slate-200 rounded-md">
                <label htmlFor="year-select-p3" className="text-slate-700 font-medium shrink-0">Seleccionar Año:</label>
                <select 
                id="year-select-p3"
                value={selectedYear} 
                onChange={(e) => onYearChange(parseInt(e.target.value))}
                className="bg-white border border-slate-400 text-slate-800 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 w-full sm:w-auto shadow-sm"
                >
                {years.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
            </div>

            {error && <div className="p-3 mb-4 rounded-md text-sm bg-red-100 text-red-700 border border-red-300">{error}</div>}
            
            {isLoading && <div className="flex flex-col justify-center items-center py-12"><IconLoader className="h-12 w-12"/> <span className="ml-4 mt-3 text-slate-500 text-lg">Cargando datos de la tabla para {selectedYear}...</span></div>}
            
            {!isLoading && annualTableData && (
                <>
                {renderTable("Operational Highlights", annualTableData.operational_table, "op")}
                {renderTable("Financial Highlights", annualTableData.financial_table, "fin")}
                </>
            )}
            {!isLoading && !annualTableData && !error && 
                <div className="text-center py-10 px-4 bg-slate-100 border border-slate-200 rounded-md">
                    <IconInformationCircle className="mx-auto h-12 w-12 text-blue-500 mb-3"/>
                    <p className="text-slate-700 text-lg">No hay datos de tabla para mostrar para el año {selectedYear}.</p>
                    <p className="text-sm text-slate-500 mt-1">Esto puede deberse a que la extracción no se ha completado o no hay informes procesados con éxito para este año.</p>
                </div>
            }
        </SubCard>
    );
};

const Point4DataHandling = () => ( 
    <SubCard title="Punto 4: Manejo de Variabilidad, Fallbacks y Estandarización">
        <div className="space-y-5 text-slate-700 leading-relaxed text-sm">
            <p>El sistema está diseñado para abordar la diversidad en los formatos de los informes financieros y la posible ausencia de datos mediante las siguientes estrategias implementadas en el backend:</p>
            
            <div className="mt-4 p-4 bg-white border border-blue-200 rounded-lg shadow-sm">
                <h4 className="font-semibold text-blue-700 mb-1.5 text-md">Manejo de Formatos Variables:</h4>
                <p className="text-slate-600">La extracción de métricas se delega a un Modelo de Lenguaje Grande (LLM - Gemini). Los LLMs son inherentemente flexibles y pueden comprender y extraer información de texto aunque la estructura, el layout y la redacción varíen entre documentos. El diseño de "prompts" efectivos (`ai_prompts.py`) es crucial para guiar al LLM a través de esta variabilidad.</p>
            </div>

            <div className="mt-4 p-4 bg-white border border-blue-200 rounded-lg shadow-sm">
                <h4 className="font-semibold text-blue-700 mb-1.5 text-md">Mecanismo de Respaldo (Fallback) para Datos Faltantes:</h4>
                <p className="text-slate-600">Si el LLM no puede encontrar una métrica específica o su valor (trimestral o YTD) en un informe, se le instruye (a través del prompt) que devuelva explícitamente la cadena <code className="bg-slate-200 text-xs px-1.5 py-0.5 rounded text-orange-700 font-mono">"Not found"</code>. Este valor se almacena tal cual en la base de datos y se refleja en las visualizaciones, indicando de forma transparente qué datos no pudieron ser extraídos y evitando la invención de información.</p>
            </div>

            <div className="mt-4 p-4 bg-white border border-blue-200 rounded-lg shadow-sm">
                <h4 className="font-semibold text-blue-700 mb-1.5 text-md">Estandarización de la Estructura de Salida:</h4>
                <p className="text-slate-600">Independientemente del formato del PDF de origen, la estructura de los datos finales se normaliza para asegurar consistencia. Esto se logra mediante:</p>
                <ul className="list-disc list-inside pl-5 mt-2 text-xs text-slate-500 space-y-1">
                    <li>**Modelos Pydantic (`schemas.py`):** Definen esquemas de datos estrictos para la entrada y salida de cada componente.</li>
                    <li>**Prompt al LLM:** Solicita la salida en un formato JSON específico y predefinido.</li>
                    <li>**Lógica de Backend (`_standardize_llm_output`):** Valida y transforma la respuesta del LLM para que se ajuste a los esquemas.</li>
                </ul>
            </div>
        </div>
    </SubCard>
);

const Point5ValidationAccuracy = ({ summaryData, isLoadingOverallSummary }) => ( 
     <SubCard title="Punto 5: Validación y Precisión de Datos">
        <div className="space-y-5 text-slate-700 text-sm">
            <p>Se ha implementado un mecanismo de validación cuantitativo para evaluar la completitud de los datos extraídos de cada informe. Este se representa como un puntaje de precisión (%).</p>
            
            {isLoadingOverallSummary && <div className="flex justify-center py-6"><IconLoader /> <span className="ml-3">Cargando datos de resumen...</span></div>}
            
            {!isLoadingOverallSummary && summaryData && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 my-5">
                    <MetricDisplay 
                        label="Precisión Promedio General" 
                        value={summaryData.average_accuracy !== null && summaryData.average_accuracy !== undefined ? `${summaryData.average_accuracy.toFixed(1)}%` : 'N/A'} 
                        valueColor="text-orange-600" 
                        size="large"
                        unit="(de informes procesados)"
                    />
                    <MetricDisplay 
                        label="Informes Procesados con Éxito" 
                        value={summaryData.reports_processed_successfully} 
                        valueColor="text-green-600" 
                        size="large"
                        unit="(total o parcial)"
                    />
                </div>
            )}

            <div className="mt-4 p-4 bg-white border border-blue-200 rounded-lg shadow-sm">
                <h4 className="font-semibold text-blue-700 mb-1.5 text-md">Metodología de Cálculo del Puntaje de Precisión:</h4>
                <ul className="list-disc list-inside pl-4 space-y-1.5 text-slate-600">
                    <li>Se utiliza una lista predefinida de métricas clave esperadas (configuradas en `ai_prompts.py`).</li>
                    <li>Para cada informe, se verifica si el LLM pudo inferir año y trimestre, y si encontró valores (no <code className="bg-slate-200 text-xs px-1 py-0.5 rounded text-orange-700 font-mono">"Not found"</code>) para las métricas esperadas (trimestral y YTD).</li>
                    <li>El puntaje es: <code className="bg-slate-200 text-sm mt-1 inline-block px-2 py-1 rounded text-orange-700 font-mono">(Campos Válidos / Campos Esperados) * 100</code>.</li>
                    <li>Refleja la <span className="font-semibold text-slate-800">completitud</span> de la extracción contra el objetivo. No valida la exactitud numérica de los valores.</li>
                </ul>
            </div>
             <p className="text-slate-500 mt-4 text-xs italic">El puntaje de precisión de cada informe individual se puede ver en los endpoints <code className="bg-slate-200 px-1 py-0.5 rounded text-orange-700 font-mono">/summary</code> y <code className="bg-slate-200 px-1 py-0.5 rounded text-orange-700 font-mono">/extracted-data/{"{id}"}</code>.</p>
        </div>
    </SubCard>
);


// --- Tarea 1 Componente Principal ---
const Task1FinancialExtraction = () => {
  const [activeSubTask, setActiveSubTask] = useState('point3'); 
  const [fetchInfo, setFetchInfo] = useState({ 
    targetSite: "https://torexgold.com/investors/financial-reports/",
    yearRange: "2021-2024",
    reportsIdentified: 0, 
    status: "Listo para iniciar", 
  });
  const [annualTableData, setAnnualTableData] = useState(null);
  const [selectedYearForTable, setSelectedYearForTable] = useState(new Date().getFullYear() - 1);
  const [isLoadingTable, setIsLoadingTable] = useState(false);
  const [tableError, setTableError] = useState(null);
  const [isExtractingBackend, setIsExtractingBackend] = useState(false);
  const [extractionUserMessage, setExtractionUserMessage] = useState(null);
  
  const [overallSummaryData, setOverallSummaryData] = useState(null);
  const [isLoadingOverallSummary, setIsLoadingOverallSummary] = useState(false);


  const yearsForDropdown = [2024, 2023, 2022, 2021];

  const showUserAlert = (message, type = 'info', duration = 7000) => { 
    setExtractionUserMessage({ text: message, type });
    setTimeout(() => setExtractionUserMessage(null), duration);
  };

  const triggerExtractionBackend = async () => {
    setIsExtractingBackend(true);
    showUserAlert("Iniciando proceso de obtención y extracción de informes en el backend...", "info");
    setTableError(null); 
    setFetchInfo(prev => ({ ...prev, status: "Procesando extracción..." }));
    try {
      const response = await fetch(`${API_BASE_URL}/reports/trigger-extraction`, { method: 'POST' });
      const result = await response.json(); 
      if (!response.ok) throw new Error(result.detail || `Error HTTP: ${response.status}`);
      
      setFetchInfo(prev => ({ 
        ...prev, 
        reportsIdentified: result.reports_identified_count, 
        status: "Proceso de extracción en segundo plano iniciado." 
      }));
      showUserAlert(result.message, "success");
      
      setTimeout(() => {
        fetchOverallSummaryDataInternal(); 
        fetchAnnualTableDataInternal(selectedYearForTable); 
      }, 15000); 
    } catch (e) {
      console.error("Error triggering extraction:", e);
      setFetchInfo(prev => ({ ...prev, status: "Error en la extracción." }));
      showUserAlert(`Error al disparar extracción: ${e.message}`, "error");
    } finally {
      setIsExtractingBackend(false);
    }
  };

  const fetchAnnualTableDataInternal = useCallback(async (year) => { 
    if (!year) return;
    setIsLoadingTable(true);
    setTableError(null);
    setAnnualTableData(null); 
    try {
      const response = await fetch(`${API_BASE_URL}/reports/annual-table/${year}`);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({detail: `Error HTTP: ${response.status}`}));
        if (response.status === 404) {
          throw new Error(errorData.detail || `No hay datos consolidados para el año ${year}. Asegúrate de que la extracción se haya completado y los informes estén procesados.`);
        }
        throw new Error(errorData.detail || `Error HTTP: ${response.status}`);
      }
      const data = await response.json();
      setAnnualTableData(data);
    } catch (e) {
      console.error(`Error fetching annual table for ${year}:`, e);
      setTableError(e.message);
    } finally {
      setIsLoadingTable(false);
    }
  }, []);

  const fetchOverallSummaryDataInternal = useCallback(async () => { 
    setIsLoadingOverallSummary(true);
    try {
      const response = await fetch(`${API_BASE_URL}/reports/summary`);
      if (!response.ok) {
        throw new Error(`Error HTTP: ${response.status} al cargar resumen general.`);
      }
      const data = await response.json();
      setOverallSummaryData(data); 
    } catch (e) {
      console.error("Error fetching overall summary:", e);
    } finally {
      setIsLoadingOverallSummary(false);
    }
  }, []);


  useEffect(() => {
    fetchOverallSummaryDataInternal();
    fetchAnnualTableDataInternal(selectedYearForTable);
  }, [selectedYearForTable, fetchAnnualTableDataInternal, fetchOverallSummaryDataInternal]);


  const subTaskComponents = {
    point1: <Point1WebsiteInfo />,
    point2: <Point2FetchProcess 
                fetchInfo={fetchInfo} 
                onTriggerExtraction={triggerExtractionBackend} 
                isExtracting={isExtractingBackend}
                extractionMessage={extractionUserMessage}
            />,
    point3: <Point3MetricTables 
                annualTableData={annualTableData} 
                selectedYear={selectedYearForTable}
                onYearChange={setSelectedYearForTable}
                years={yearsForDropdown}
                isLoading={isLoadingTable}
                error={tableError}
            />,
    point4: <Point4DataHandling />, 
    point5: <Point5ValidationAccuracy summaryData={overallSummaryData} isLoadingOverallSummary={isLoadingOverallSummary} />
  };

  const subTaskNavItems = [
    { id: 'point1', label: '1. Sitio Web', icon: <IconLink /> },
    { id: 'point2', label: '2. Obtención', icon: <IconListBullet /> },
    { id: 'point3', label: '3. Métricas', icon: <IconTableCells /> },
    { id: 'point4', label: '4. Manejo Datos', icon: <IconWrenchScrewdriver /> },
    { id: 'point5', label: '5. Validación', icon: <IconShieldCheck /> },
  ];

  return (
    <MainCard title="Tarea 1: Extracción Automatizada de Informes Financieros" icon={<IconDocumentChartBar />}>
        <div className="mb-6 flex flex-wrap gap-2 border-b-2 border-blue-200 pb-3">
            {subTaskNavItems.map(item => (
                <SubTabButton 
                    key={item.id}
                    label={item.label}
                    icon={item.icon}
                    isActive={activeSubTask === item.id}
                    onClick={() => setActiveSubTask(item.id)}
                />
            ))}
        </div>
        <div className="mt-4 min-h-[400px] p-1"> 
            {subTaskComponents[activeSubTask]}
        </div>
    </MainCard>
  );
};


// --- Tarea 2 y 3 Placeholders ---
const TaskPlaceholder = ({ title, icon, description }) => (
  <MainCard title={title} icon={icon}>
    <div className="text-center text-slate-500 py-10">
      <div className="mb-4 text-blue-500/70">{React.cloneElement(icon, { className: "w-16 h-16 mx-auto" })}</div>
      <p className="text-lg">{description}</p>
      <p className="text-sm mt-2">(Funcionalidad pendiente de implementación)</p>
    </div>
  </MainCard>
);


// --- Componente Principal App ---
function App() {
  const [activeTask, setActiveTask] = useState('task1'); 

  const renderActiveTask = () => {
    switch (activeTask) {
      case 'task1':
        return <Task1FinancialExtraction />; 
      case 'task2':
        return <TaskPlaceholder 
                  title="Tarea 2: Extracción y Clasificación de Imágenes" 
                  icon={<IconPhoto />}
                  description="Esta sección mostrará los resultados de la extracción y clasificación de imágenes de documentos." 
                />;
      case 'task3':
        return <TaskPlaceholder 
                  title="Tarea 3: Visión por Computadora Geoespacial" 
                  icon={<IconMapPin />}
                  description="Aquí se visualizarán los resultados del análisis de mapas y extracción de coordenadas." 
                />;
      default:
        return <Task1FinancialExtraction />;
    }
  };

  const mainTabNavItems = [
    { id: 'task1', label: 'Tarea 1: Informes', icon: <IconDocumentChartBar className="w-5 h-5 sm:w-6 sm:h-6"/> },
    { id: 'task2', label: 'Tarea 2: Imágenes', icon: <IconPhoto className="w-5 h-5 sm:w-6 sm:h-6"/> },
    { id: 'task3', label: 'Tarea 3: Geoespacial', icon: <IconMapPin className="w-5 h-5 sm:w-6 sm:h-6"/> },
  ];

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800 p-4 sm:p-6 md:p-8 font-sans antialiased">
      <div className="max-w-7xl mx-auto"> 
        <header className="mb-10 text-center">
          <h1 className="text-3xl sm:text-4xl font-bold text-blue-700 py-2"> {/* Título más pequeño */}
            {APP_TITLE}
          </h1>
        </header>

        <nav className="mb-10 flex flex-col sm:flex-row justify-center rounded-lg p-1.5 bg-white shadow-md border border-slate-200 max-w-xl mx-auto">
          {mainTabNavItems.map(item => (
            <TabButton 
                key={item.id}
                label={item.label} 
                icon={React.cloneElement(item.icon, { className: `w-5 h-5 ${activeTask === item.id ? 'text-white' : 'text-blue-600'}` })}
                isActive={activeTask === item.id} 
                onClick={() => setActiveTask(item.id)} 
            />
          ))}
        </nav>

        <main>
          {renderActiveTask()}
        </main>
        
        <footer className="text-center mt-20 mb-10 text-xs text-slate-500">
          <p>Panel de Resultados | GeoAI Technical Test</p>
        </footer>
      </div>
    </div>
  );
}

const TabButton = ({ label, icon, isActive, onClick }) => (
  <button
    onClick={onClick}
    className={`flex-1 flex items-center justify-center sm:justify-start space-x-2 sm:space-x-3 px-3 sm:px-4 py-2.5 rounded-md font-semibold text-xs sm:text-sm transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-white
                ${isActive 
                  ? 'bg-blue-600 text-white shadow-lg ring-blue-500' 
                  : 'bg-transparent text-slate-600 hover:bg-slate-100 hover:text-blue-700 ring-transparent'}`}
  >
    {icon}
    <span>{label}</span>
  </button>
);

export default App;

