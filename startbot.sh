#!/bin/sh

echo "TG to Num Bot starting..."
ls

BUCKET_PATH="/data"

if [ -d "$BUCKET_PATH" ]; then
    echo "Files in your Storage Bucket:"
    ls -lah "$BUCKET_PATH"
else
    echo "Bucket not found at $BUCKET_PATH"
    echo "Check your Space settings to ensure the Bucket is mounted."
fi

# python3 bott.py
#while true
#do
#    echo "[`date`] Starting bot..."
    
#    python3 bott.py
#
#    echo "[`date`] Bot crashed or stopped. Restarting in 5 seconds..."
    
#    sleep 5
#done
