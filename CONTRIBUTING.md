# Contributing to PicoChess

¡Gracias por tu interés en contribuir a PicoChess!

## Cómo contribuir

1. **Fork** el repositorio
2. **Clona** tu fork localmente
3. **Crea** una rama para tu feature: `git checkout -b mi-nueva-feature`
4. **Realiza** tus cambios
5. **Ejecuta** los tests: `pytest tests/`
6. **Commit** tus cambios: `git commit -am 'Añadir nueva feature'`
7. **Push** a la rama: `git push origin mi-nueva-feature`
8. **Crea** un Pull Request

## Estilo de código

- Usa **Black** para formatear el código: `black .`
- Sigue **PEP 8**
- Añade **docstrings** a funciones y clases
- Escribe **tests** para nuevas funcionalidades

## Reportar bugs

Usa GitHub Issues para reportar bugs. Incluye:
- Descripción del problema
- Pasos para reproducir
- Comportamiento esperado vs actual
- Información del sistema (OS, Python version, etc.)

## Desarrollo local

```bash
# Instalar dependencias
pip install -r requirements.txt
pip install -r test-requirements.txt

# Ejecutar tests
pytest tests/

# Formatear código
black .

# Linting
flake8 .
```