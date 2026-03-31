#!/bin/sh

echo "TG to Num Bot starting..."


# /data directory check karo, agar nahi hai toh banao
if [ ! -d "/data" ]; then
    mkdir -p /data
fi

# config.json create karo aur content likho
cat > /data/config.json <<EOL
{
    "id": "000"
}
EOL

echo "config.json successfully created in /data"

# python3 bott.py
#while true
#do
#    echo "[`date`] Starting bot..."
    
#    python3 bott.py
#
#    echo "[`date`] Bot crashed or stopped. Restarting in 5 seconds..."
    
#    sleep 5
#done
