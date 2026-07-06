@echo off
cd /d E:\claude\konkur-coach
:loop
echo [%date% %time%] starting bot >> bot_run.log
"E:\claude\konkur-coach\.venv\Scripts\python.exe" -u main.py >> bot_run.log 2>&1
echo [%date% %time%] bot exited, restarting in 5s >> bot_run.log
timeout /t 5 /nobreak > nul
goto loop
