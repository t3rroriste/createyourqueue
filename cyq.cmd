@echo off
rem Raccourci : .\cyq <verbe>  ->  outils\cyq.ps1
rem Sans lui, il faudrait taper la ligne powershell complete a chaque fois.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\cyq.ps1" %*
