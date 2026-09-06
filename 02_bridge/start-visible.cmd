@echo off
rem Launch visible NX with a project-local custom directory whose startup folder
rem holds the dispatcher. NX loads startup libraries itself; no manual Play Journal.
rem On this ARM64 host the x64 .NET runtime lives in a side-by-side directory that
rem the NX loader does not search, so the x64 process is pointed at it explicitly.
setlocal
set "UGII_CUSTOM_DIRECTORY_FILE=%~dp0custom_dirs.dat"
set "ONLINE_MACHINING_ROOT=%~dp0.."
set "DOTNET_ROOT=C:\Program Files\dotnet\x64"
cd /d "%~dp0.."
start "" "C:\Program Files\Siemens\NX2506\NXBIN\ugraf.exe" -nx
