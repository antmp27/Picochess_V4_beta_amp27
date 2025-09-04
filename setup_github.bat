@echo off
echo Configurando repositorio Git para PicoChess...

REM Inicializar repositorio Git si no existe
if not exist .git (
    git init
    echo Repositorio Git inicializado.
)

REM Agregar todos los archivos respetando .gitignore
git add .

REM Hacer commit inicial
git commit -m "Initial commit: PicoChess project without engine binaries"

echo.
echo Repositorio preparado. Para subir a GitHub:
echo 1. Crea un repositorio en GitHub
echo 2. Ejecuta: git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
echo 3. Ejecuta: git branch -M main
echo 4. Ejecuta: git push -u origin main

pause