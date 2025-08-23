#!/usr/bin/env python3
"""
Script para preparar el proyecto PicoChess para GitHub
"""

import os
import shutil
import subprocess
import sys

def run_command(cmd, cwd=None):
    """Ejecuta un comando y retorna el resultado"""
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def main():
    print("🚀 Preparando proyecto PicoChess para GitHub...")
    
    # Verificar que estamos en el directorio correcto
    if not os.path.exists("picochess.py"):
        print("❌ Error: No se encuentra picochess.py. Ejecuta este script desde el directorio raíz del proyecto.")
        sys.exit(1)
    
    # Limpiar archivos innecesarios
    print("🧹 Limpiando archivos innecesarios...")
    
    # Archivos y directorios a limpiar
    cleanup_patterns = [
        "__pycache__",
        "*.pyc",
        "*.pyo",
        ".pytest_cache",
        ".coverage",
        "htmlcov",
        ".tox",
        "build",
        "dist",
        "*.egg-info"
    ]
    
    for pattern in cleanup_patterns:
        success, stdout, stderr = run_command(f"find . -name '{pattern}' -exec rm -rf {{}} +")
        if not success and "find" in stderr:
            # Fallback para Windows
            if pattern == "__pycache__":
                for root, dirs, files in os.walk("."):
                    if "__pycache__" in dirs:
                        shutil.rmtree(os.path.join(root, "__pycache__"))
    
    # Verificar estructura de archivos importantes
    important_files = [
        "README.md",
        "LICENSE", 
        "requirements.txt",
        "setup.py",
        ".gitignore",
        "CONTRIBUTING.md"
    ]
    
    print("📋 Verificando archivos importantes...")
    for file in important_files:
        if os.path.exists(file):
            print(f"  ✅ {file}")
        else:
            print(f"  ⚠️  {file} - No encontrado")
    
    # Verificar estructura de GitHub
    github_files = [
        ".github/workflows/python-app.yml",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/feature_request.md",
        ".github/pull_request_template.md"
    ]
    
    print("🐙 Verificando archivos de GitHub...")
    for file in github_files:
        if os.path.exists(file):
            print(f"  ✅ {file}")
        else:
            print(f"  ⚠️  {file} - No encontrado")
    
    # Mostrar estadísticas del proyecto
    print("\n📊 Estadísticas del proyecto:")
    
    # Contar archivos Python
    py_files = 0
    for root, dirs, files in os.walk("."):
        if ".git" in root or "__pycache__" in root:
            continue
        py_files += len([f for f in files if f.endswith(".py")])
    
    print(f"  📄 Archivos Python: {py_files}")
    
    # Contar líneas de código
    success, stdout, stderr = run_command("find . -name '*.py' -not -path './.git/*' -not -path './__pycache__/*' | xargs wc -l")
    if success and stdout:
        lines = stdout.strip().split('\n')[-1].split()[0]
        print(f"  📏 Líneas de código: {lines}")
    
    print("\n✅ Proyecto preparado para GitHub!")
    print("\n📝 Próximos pasos:")
    print("1. Crear repositorio en GitHub")
    print("2. git init")
    print("3. git add .")
    print("4. git commit -m 'Initial commit'")
    print("5. git remote add origin <tu-repo-url>")
    print("6. git push -u origin main")
    print("\n🎉 ¡Listo para compartir tu proyecto!")

if __name__ == "__main__":
    main()