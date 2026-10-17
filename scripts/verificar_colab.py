import sys
import importlib.util
import torch

print("=== ESTADO DE GOOGLE COLAB ===")
print("Python:", sys.version.split()[0])

for paquete in ["requests", "PIL", "torch"]:
    disponible = importlib.util.find_spec(paquete) is not None
    print(f"{paquete}: {'INSTALADO' if disponible else 'NO INSTALADO'}")

print("\n=== ESTADO DE GPU ===")
print("CUDA disponible:", torch.cuda.is_available())

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))

print("\nCONEXION CON COLAB: CORRECTA")
