import requests

URL = "https://api.openverse.org/v1/images/"

print("=== DIAGNÓSTICO DE OPENVERSE ===", flush=True)

try:
    respuesta = requests.get(
        URL,
        params={
            "q": "river pollution",
            "page_size": 5
        },
        headers={
            "User-Agent": "HuanucoEcoGuardAI/1.0 (academic research)"
        },
        timeout=30
    )

    print("Código HTTP:", respuesta.status_code)
    print("URL consultada:", respuesta.url)
    print("Respuesta:", respuesta.text[:1500])

    if respuesta.ok:
        datos = respuesta.json()
        print("Resultados totales:", datos.get("result_count"))
        print("Resultados recibidos:", len(datos.get("results", [])))

except Exception as error:
    print("Error:", type(error).__name__, str(error))
