# PicoChess - Fork Mejorado

[![Python application](https://github.com/antmp27/picochess-keyboard/actions/workflows/python-app.yml/badge.svg)](https://github.com/antmp27/picochess-keyboard/actions/workflows/python-app.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

Transforma tu Raspberry Pi o cualquier computadora basada en Debian en una computadora de ajedrez. Este fork se enfoca en modernizar el código con arquitectura asíncrona y dependencias actualizadas.

## 🚀 Instalación Rápida

```bash
# Clonar el repositorio
git clone https://github.com/antmp27/picochess-keyboard.git
cd picochess

# Instalar (Linux/macOS)
./install.sh

# Instalar (Windows)
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements.txt
```

## 🎮 Uso

```bash
# Activar entorno virtual
source venv/bin/activate  # Linux/macOS
# o
venv\\Scripts\\activate   # Windows

# Ejecutar PicoChess
python picochess.py

# Abrir navegador en http://localhost:8080
```

## ✨ Características

- 🌐 **Interfaz Web** - Juega desde cualquier navegador
- 🎯 **Tableros Electrónicos** - Compatible con DGT, Certabo, Chesslink, Chessnut, Ichessone
- ⚡ **Arquitectura Asíncrona** - Mejor rendimiento y escalabilidad
- 🔄 **Dependencias Actualizadas** - Python moderno con librerías actuales
- 🧠 **Motores Incluidos** - Stockfish 17 y Leela Chess Zero
- 🎓 **PicoTutor** - Análisis y evaluación de partidas

## 🛠️ Desarrollo

```bash
# Instalar dependencias de desarrollo
pip install -r test-requirements.txt

# Ejecutar tests
pytest tests/

# Formatear código
black .

# Linting
flake8 .
```

## 📋 Requisitos

- Python 3.8+
- Raspberry Pi 3/4/5 (aarch64) o PC Debian/Ubuntu (x86_64)
- 32GB+ SD card (para Raspberry Pi)

## 🤝 Contribuir

¡Las contribuciones son bienvenidas! Lee [CONTRIBUTING.md](CONTRIBUTING.md) para más detalles.

1. Fork el proyecto
2. Crea tu rama de feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo la Licencia GPL v3 - ver [LICENSE](LICENSE) para detalles.

## 🙏 Reconocimientos

- Proyecto original PicoChess
- Comunidad de [PicoChess Google Group](https://groups.google.com/g/picochess)
- Motores de ajedrez Stockfish y Leela Chess Zero

## 📞 Soporte

- 🐛 [Reportar bugs](https://github.com/antmp27/picochess-keyboard/issues)
- 💬 [Discusiones](https://github.com/antmp27/picochess-keyboard/discussions)
- 📧 [Google Group](https://groups.google.com/g/picochess)