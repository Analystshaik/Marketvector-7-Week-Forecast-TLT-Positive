@echo off
cd /d "%~dp0"

python build_cloud_database.py ^
  --source "C:\MarketVector\Database\ibkr_market_data.sqlite" ^
  --output "data\streamlit_market_data.sqlite" ^
  --weekly ^
  --history-years 8

pause
