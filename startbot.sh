#!/bin/sh

echo "TG to Num Bot starting..."

while true
do
    echo "[`date`] Starting bot..."
    
    python3 bott.py

    echo "[`date`] Bot crashed or stopped. Restarting in 5 seconds..."
    
    sleep 5
done
