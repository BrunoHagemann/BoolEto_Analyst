@echo off
title Interpretador de Arquivos .BOOL
chcp 65001 > nul

:: 1. Garante que o terminal abra na pasta exata onde o compilador esta salvo
cd /d "%~dp0"

:: 2. Trava de seguranca: Verifica se o usuario realmente arrastou um arquivo
if "%~1"=="" (
    echo ===============================================================
    echo [ERRO] Nenhum arquivo foi detectado!
    echo.
    echo Para usar o sistema, clique em um arquivo com extensao .bool,
    echo arraste-o e solte-o em cima do icone deste executavel.
    echo ===============================================================
    echo.
    pause
    exit /b
)

:: 3. Executa o compilador passando o arquivo que foi solto
echo ===============================================================
echo Executando o script: "%~nx1"
echo ===============================================================
echo.

python Compliador_Bool.py "%~1"

echo.
echo ===============================================================
echo ✅ Processo finalizado.
pause