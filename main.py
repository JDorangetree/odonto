import os
import io
import json
from dotenv import load_dotenv
import google.generativeai as genai
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from google.api_core import exceptions as google_exceptions
from pydub import AudioSegment



BASE_DIR = os.path.dirname(os.path.abspath(__name__))
PROMPTS_FILE_PATH = os.path.join(BASE_DIR, 'Prompts', 'prompts.json')

# Carga las variables de entorno desde un archivo .env
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- Configurar genai globalmente con la clave (si existe) ---
if GOOGLE_API_KEY:
     genai.configure(api_key=GOOGLE_API_KEY)
     print("API Key de Gemini cargada desde el entorno.")
else:
     print("ADVERTENCIA: GOOGLE_API_KEY no configurada. El endpoint /generate/ no funcionará.")



# --- Cargar los prompts desde el archivo JSON al inicio ---
LOADED_PROMPTS: dict = {}
try:
    if os.path.exists(PROMPTS_FILE_PATH):
        with open(PROMPTS_FILE_PATH, 'r', encoding='utf-8') as f: # Usa encoding='utf-8'
            LOADED_PROMPTS = json.load(f)
        print(f"Prompts cargados desde {PROMPTS_FILE_PATH}")
    else:
        print(f"ADVERTENCIA: El archivo de prompts no se encontró en {PROMPTS_FILE_PATH}. Algunos endpoints podrían no funcionar correctamente.")
except json.JSONDecodeError:
    print(f"ERROR: El archivo {PROMPTS_FILE_PATH} no es un JSON válido.")
    # Puedes decidir salir o usar un diccionario vacío
    LOADED_PROMPTS = {}
except Exception as e:
    print(f"ERROR inesperado al cargar prompts desde {PROMPTS_FILE_PATH}: {e}")
    LOADED_PROMPTS = {}


# Define el modelo de datos para la solicitud entrante de Gemini (AHORA SIN LA CLAVE)
class GeminiRequest(BaseModel):
    # Puedes agregar un campo opcional para especificar qué prompt usar del archivo
    #prompt_key: Optional[str] = None # Clave para seleccionar un prompt del archivo
    user_description_input: str # La descripción del producto introducida para resumir


# Crea la instancia de la aplicación FastAPI
app = FastAPI(
    title="odontograma" \
    " con Gemini" ,
    description="API para crear odontograma a partir del audio/dictado de un odontologo",
    version="0.1.0",
)

origins = [
    "http://localhost:8000",  # Ejemplo si tu frontend corre en localhost:8000
    "http://localhost:3000",  # Ejemplo si usas React en localhost:3000
    "http://127.0.0.1:8000",
    "http://127.0.0.1:3000",
    "null",
    "odontograma-g7hyemacauerc5ac.canadacentral-01.azurewebsites.net"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Permite todos los métodos (GET, POST, etc.)
    allow_headers=["*"], # Permite todos los encabezados
)

@app.post("/analyze-audio-gemini-json/")
async def analyze_audio_gemini(
    audio_file: UploadFile = File(...)
    #prompt_text: str = "Describe el contenido principal de este audio."
):
    """
    Recibe un archivo de audio y lo procesa con Google Gemini para análisis multimodal.
    No es un servicio de transcripción pura, sino para entender el audio en un contexto.
    """
    if not audio_file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="El archivo subido no es un archivo de audio válido.")

    #if not audio_file.content_type in ["audio/wav", "audio/mp3", "audio/mpeg"]:
    #    #print(f"Tipo de audio recibido: {audio_file.content_type}")
    #    raise HTTPException(status_code=400, detail=f"Tipo de audio no soportado por Gemini para carga directa: {audio_file.content_type}. Intenta con WAV o MP3.")

    original_mime_type = audio_file.content_type

    try:
        audio_content = await audio_file.read()

        if original_mime_type == "audio/webm":
            # Leer el audio WebM desde bytes
            audio_segment = AudioSegment.from_file(io.BytesIO(audio_content), format="webm")
            
            # Exportar a MP3 en un buffer de bytes
            mp3_buffer = io.BytesIO()
            audio_segment.export(mp3_buffer, format="mp3")
            mp3_buffer.seek(0) # Volver al inicio del buffer
            
            processed_audio_bytes = mp3_buffer.read()
            processed_mime_type = "audio/mpeg" # MP3 es audio/mpeg
        elif original_mime_type in ["audio/wav", "audio/mp3", "audio/mpeg"]:
            processed_audio_bytes = audio_content
            processed_mime_type = original_mime_type
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo de audio no soportado para procesamiento: {original_mime_type}. Soporta: WAV, MP3, MPEG, WEBM."
            )
        
        if not processed_audio_bytes:
             raise HTTPException(status_code=500, detail="Error en la preparación del audio para Gemini.")

        
        # Crear un objeto genai.upload_file para el audio
        # Nota: La API de Gemini requiere subir el archivo a su infraestructura temporal
        # para procesamiento multimodal. Esto no es para archivos muy grandes.
        uploaded_audio = genai.upload_file(io.BytesIO(processed_audio_bytes), mime_type=processed_mime_type)
        print(f"Archivo '{audio_file.filename}' subido temporalmente para Gemini.")

        # Iniciar el chat con el modelo Gemini
        model = genai.GenerativeModel('gemini-2.5-flash-preview-04-17')
        chat = model.start_chat(history=[])
        # Si el cliente especificó una clave de prompt
        prompt_text = LOADED_PROMPTS.get('dental_findings_json_list')    
        

        # Enviar el audio y el prompt al modelo
        contents = [
            prompt_text,
            uploaded_audio
        ]

        print("Enviando audio y prompt a Gemini para análisis...")
        response = await chat.send_message_async(contents) # Usar async para non-blocking I/O
        response = response.text
        
        # Eliminar el archivo subido temporalmente después de usarlo
        genai.delete_file(uploaded_audio.name)
        print(f"Archivo temporal '{uploaded_audio.name}' eliminado.")

        cleaned_json_string = response.replace("```json\n", "").replace("\n```", "")
        response = json.loads(cleaned_json_string)

        return response

    except Exception as e:
        print(f"Error al procesar el audio con Gemini: {e}")
        # En caso de error, intenta eliminar el archivo si se subió
        if 'uploaded_audio' in locals() and uploaded_audio.name:
            try:
                genai.delete_file(uploaded_audio.name)
                print(f"Archivo temporal '{uploaded_audio.name}' eliminado después de error.")
            except Exception as delete_e:
                print(f"Error al intentar eliminar el archivo temporal de Gemini: {delete_e}")
        raise HTTPException(status_code=500, detail=f"Error interno al procesar el audio con Gemini: {e}")

@app.post("/analyze-audio-gemini-doc/")
async def analyze_audio_gemini_doc(
    audio_file: UploadFile = File(...)
    #prompt_text: str = "Describe el contenido principal de este audio."
):
    """
    Recibe un archivo de audio y lo procesa con Google Gemini para análisis multimodal.
    No es un servicio de transcripción pura, sino para entender el audio en un contexto.
    """
    if not audio_file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="El archivo subido no es un archivo de audio válido.")

    if not audio_file.content_type in ["audio/wav", "audio/mp3", "audio/mpeg"]:
        raise HTTPException(status_code=400, detail=f"Tipo de audio no soportado por Gemini para carga directa: {audio_file.content_type}. Intenta con WAV o MP3.")


    try:
        # Leer el contenido del audio
        audio_bytes = await audio_file.read()

        # Crear un objeto genai.upload_file para el audio
        # Nota: La API de Gemini requiere subir el archivo a su infraestructura temporal
        # para procesamiento multimodal. Esto no es para archivos muy grandes.
        uploaded_audio = genai.upload_file(io.BytesIO(audio_bytes), mime_type=audio_file.content_type)
        print(f"Archivo '{audio_file.filename}' subido temporalmente para Gemini.")

        # Iniciar el chat con el modelo Gemini
        model = genai.GenerativeModel('gemini-2.5-flash-preview-04-17')
        chat = model.start_chat(history=[])
        # Si el cliente especificó una clave de prompt
        prompt_text = LOADED_PROMPTS.get('dental_findings_doc_list')    
        

        # Enviar el audio y el prompt al modelo
        contents = [
            prompt_text,
            uploaded_audio
        ]

        print("Enviando audio y prompt a Gemini para análisis...")
        response = await chat.send_message_async(contents) # Usar async para non-blocking I/O
        response = response.text
        
        # Eliminar el archivo subido temporalmente después de usarlo
        genai.delete_file(uploaded_audio.name)
        print(f"Archivo temporal '{uploaded_audio.name}' eliminado.")


        return response

    except Exception as e:
        print(f"Error al procesar el audio con Gemini: {e}")
        # En caso de error, intenta eliminar el archivo si se subió
        if 'uploaded_audio' in locals() and uploaded_audio.name:
            try:
                genai.delete_file(uploaded_audio.name)
                print(f"Archivo temporal '{uploaded_audio.name}' eliminado después de error.")
            except Exception as delete_e:
                print(f"Error al intentar eliminar el archivo temporal de Gemini: {delete_e}")
        raise HTTPException(status_code=500, detail=f"Error interno al procesar el audio con Gemini: {e}")


