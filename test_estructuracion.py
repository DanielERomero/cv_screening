import os
import glob
import json
from main import extraer_texto_pdf, estructurar_cv

def test_estructuracion():
    # Buscar todos los archivos PDF en la carpeta actual
    archivos_pdf = glob.glob("*.pdf")
    
    if not archivos_pdf:
        print("[-] No se encontraron archivos PDF en la carpeta actual.")
        return

    print(f"[*] Se encontraron {len(archivos_pdf)} archivo(s) PDF: {', '.join(archivos_pdf)}\n")

    for ruta_al_pdf in archivos_pdf:
        print(f"\n[*] --- Procesando: {ruta_al_pdf} ---")
        
        # 1. Extraer el texto
        print("[*] Paso 1: Extrayendo texto...")
        texto = extraer_texto_pdf(ruta_al_pdf)
        
        if not texto:
            print(f"[-] No se pudo extraer texto de {ruta_al_pdf}. Saltando al siguiente.")
            continue
            
        print(f"[+] Texto extraído. Longitud: {len(texto)} caracteres.")
        
        # 2. Estructurar el CV
        print("[*] Paso 2: Ejecutando estructurar_cv()...")
        resultado_json = estructurar_cv(texto)
        
        print("\n" + "="*50)
        print(f"--- RESULTADO ESTRUCTURADO ({ruta_al_pdf}) ---")
        print("="*50)
        
        # Mostrar el resultado JSON de manera más bonita y legible
        print(json.dumps(resultado_json, indent=4, ensure_ascii=False))
        
        print("="*50 + "\n")
        
        # 3. Guardar el resultado en un archivo JSON
        nombre_base = os.path.splitext(ruta_al_pdf)[0]
        nombre_archivo_json = f"{nombre_base}_estructurado.json"
        
        try:
            with open(nombre_archivo_json, 'w', encoding='utf-8') as f:
                json.dump(resultado_json, f, indent=4, ensure_ascii=False)
            print(f"[+] Resultado guardado exitosamente en: {nombre_archivo_json}")
        except Exception as e:
            print(f"[-] Error al guardar el archivo JSON: {e}")

if __name__ == "__main__":
    test_estructuracion()
