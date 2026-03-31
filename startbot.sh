#!/bin/sh

echo "TG to Num Bot starting..."
ls


# Bucket ka mounted path
BUCKET_PATH="/mnt/data"

echo "Listing all files in bucket: $BUCKET_PATH"
echo "-----------------------------------------"

# Recursive list
find "$BUCKET_PATH" -type f

echo "-----------------------------------------"
echo "Done!"

while true
do
    echo "[`date`] Starting bot..."
    
    python3 bott.py

    echo "[`date`] Bot crashed or stopped. Restarting in 5 seconds..."
    
    sleep 5
done
