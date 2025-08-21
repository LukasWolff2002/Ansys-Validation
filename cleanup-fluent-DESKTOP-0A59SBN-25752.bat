echo off
set LOCALHOST=%COMPUTERNAME%
set KILL_CMD="C:\PROGRA~1\ANSYSI~1\ANSYSS~1\v252\fluent/ntbin/win64/winkill.exe"

start "tell.exe" /B "C:\PROGRA~1\ANSYSI~1\ANSYSS~1\v252\fluent\ntbin\win64\tell.exe" DESKTOP-0A59SBN 51913 CLEANUP_EXITING
timeout /t 1
"C:\PROGRA~1\ANSYSI~1\ANSYSS~1\v252\fluent\ntbin\win64\kill.exe" tell.exe
if /i "%LOCALHOST%"=="DESKTOP-0A59SBN" (%KILL_CMD% 25860) 
if /i "%LOCALHOST%"=="DESKTOP-0A59SBN" (%KILL_CMD% 20528) 
if /i "%LOCALHOST%"=="DESKTOP-0A59SBN" (%KILL_CMD% 17556) 
if /i "%LOCALHOST%"=="DESKTOP-0A59SBN" (%KILL_CMD% 11748) 
if /i "%LOCALHOST%"=="DESKTOP-0A59SBN" (%KILL_CMD% 25752) 
if /i "%LOCALHOST%"=="DESKTOP-0A59SBN" (%KILL_CMD% 11456)
del "C:\Users\MBX\Desktop\Ansys-Validation\cleanup-fluent-DESKTOP-0A59SBN-25752.bat"
