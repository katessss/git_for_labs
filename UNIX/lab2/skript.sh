#!/bin/sh

DATA_DIR="/data"
SEQ=1 

CONTAINER_ID=$(mktemp -u XXXXXX)
echo "Starting Container $CONTAINER_ID"


LOCK_FILE="$DATA_DIR/.lockfile" 

while true; do
    TARGET_FILE=""

    # атомарная операция
    {   flock -x 42
        i=1
        while true; do
            NAME=$(printf "%03d" $i)  
            FILE_PATH="$DATA_DIR/$NAME"
            
            if [ ! -e "$FILE_PATH" ]; then 
                TARGET_FILE="$FILE_PATH"
                printf "CID: %s | SEQ: %d\n" "$CONTAINER_ID" "$SEQ" > "$TARGET_FILE" 
                break
            fi
            i=$((i+1))
        done
    } 42>"$LOCK_FILE"

    echo "[Created] $TARGET_FILE (ID: $CONTAINER_ID, SEQ: $SEQ)"

    sleep 10

    rm "$TARGET_FILE"
    echo "[Deleted] $TARGET_FILE"

    SEQ=$((SEQ+1))
done