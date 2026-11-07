@echo off
chcp 874 >nul
title REVOTECH Roof Master - Install
echo.
echo  =============================================
echo   REVOTECH Roof Master - ติดตั้งคลิกเดียว
echo  =============================================
echo.
if not exist "%~dp0REVOTECH.extension\" goto :noext

set "DEST=%APPDATA%\pyRevit\Extensions"
if not exist "%DEST%" mkdir "%DEST%"
robocopy "%~dp0REVOTECH.extension" "%DEST%\REVOTECH.extension" /E /NFL /NDL /NJH /NJS >nul
if errorlevel 8 goto :copyfail

echo  [OK] ติดตั้งเรียบร้อย! วางไฟล์ไว้ที่:
echo       %DEST%\REVOTECH.extension
echo.
echo  ขั้นต่อไป:
echo   1. ยังไม่มี pyRevit? โหลดฟรี: github.com/pyrevitlabs/pyRevit/releases
echo   2. เปิด Revit แล้วไปที่แท็บ pyRevit กด Reload
echo   3. จะได้แท็บ REVOTECH พร้อมปุ่ม Roof Master
echo.
pause
exit /b 0

:noext
echo  [X] ไม่พบโฟลเดอร์ REVOTECH.extension ข้างไฟล์นี้
echo      กรุณาแตก zip ทั้งไฟล์ก่อน แล้วค่อยดับเบิลคลิกไฟล์นี้
echo      (เปิดจากในหน้าต่าง zip ตรงๆ ไม่ได้)
echo.
pause
exit /b 1

:copyfail
echo  [X] คัดลอกไม่สำเร็จ - ลองคลิกขวาไฟล์นี้แล้ว Run as administrator
echo.
pause
exit /b 1
