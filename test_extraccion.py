import os
import glob
from main import extraer_texto_pdf

def test_extraccion():
    # Buscar todos los archivos PDF en la carpeta actual
    archivos_pdf = glob.glob("*.pdf")
    
    if not archivos_pdf:
        print("[-] No se encontraron archivos PDF en la carpeta actual.")
        return

    print(f"[*] Se encontraron {len(archivos_pdf)} archivo(s) PDF: {', '.join(archivos_pdf)}\n")

    for ruta_al_pdf in archivos_pdf:
        print(f"[*] Iniciando prueba de extracción para: {ruta_al_pdf}...")
        
        # Llamamos a la función original en main.py
        texto = extraer_texto_pdf(ruta_al_pdf)

        print("\n" + "="*40)
        print(f"--- INICIO DEL TEXTO EXTRAÍDO ({ruta_al_pdf}) ---")
        print("="*40 + "\n")
        
        print(texto)
        
        print("\n" + "="*40)
        print(f"--- FIN DEL TEXTO EXTRAÍDO ({ruta_al_pdf}) ---")
        print("="*40 + "\n")

if __name__ == "__main__":
    test_extraccion()
