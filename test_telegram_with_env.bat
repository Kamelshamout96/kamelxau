@echo off
echo Setting Telegram environment variables...
set TG_TOKEN=8512147987:AAEhK8u7a_apAENZgo4V5rP6x9vcm_OClHk
set TG_CHAT=5326666507

echo Testing Telegram connection...
py test_telegram.py
pause
