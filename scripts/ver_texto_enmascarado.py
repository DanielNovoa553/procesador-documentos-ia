import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import privacidad
from app.extractor import _limpiar_texto, _texto_del_pdf

if len(sys.argv) != 2:
    raise SystemExit("Uso: python scripts/ver_texto_enmascarado.py ruta/al/archivo.pdf")

texto = _limpiar_texto(_texto_del_pdf(Path(sys.argv[1]).read_bytes()))
enmascarado, mascara = privacidad.enmascarar(texto)
privacidad.verificar_limpio(enmascarado)
print(enmascarado)
print("\nEnmascarado:", privacidad.resumen(mascara))