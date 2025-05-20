#!/bin/bash
# emergency_shutdown.sh - Force kill all Green-Boy processes

# Text formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${RED}=== EMERGENCY SHUTDOWN OF GREEN-BOY ===${NC}"
echo -e "This script will forcefully terminate all Green-Boy bot processes"

# Get the current user
CURRENT_USER=$(whoami)

# Step 1: Find all Green-Boy processes
echo -e "\n${YELLOW}Step 1: Finding all Green-Boy processes for user ${CURRENT_USER}...${NC}"
PROCS=$(ps aux | grep "green-boy.py" | grep -v grep | grep "$CURRENT_USER")

if [ -z "$PROCS" ]; then
    echo -e "${YELLOW}No Green-Boy processes found for user ${CURRENT_USER}.${NC}"
else
    echo -e "Found the following processes:"
    echo "$PROCS"
    
    # Extract PIDs
    PIDS=$(echo "$PROCS" | awk '{print $2}')
    
    # Step 2: Kill each process
    echo -e "\n${YELLOW}Step 2: Killing processes...${NC}"
    for PID in $PIDS; do
        echo -e "Killing process $PID..."
        kill -9 $PID 2>/dev/null
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Process $PID terminated${NC}"
        else
            echo -e "${RED}✗ Failed to kill process $PID${NC}"
        fi
    done
fi

# Step 3: Clean up resources
echo -e "\n${YELLOW}Step 3: Cleaning up resources...${NC}"

# Remove lock files
LOCK_FILE="/tmp/greenboy-${CURRENT_USER}.lock"
if [ -f "$LOCK_FILE" ]; then
    rm -f "$LOCK_FILE"
    echo -e "${GREEN}✓ Removed lock file: $LOCK_FILE${NC}"
else
    echo -e "Lock file not found: $LOCK_FILE"
fi

# Calculate user-specific port
USER_PORT=$((49152 + $(echo "$CURRENT_USER" | cksum | cut -d' ' -f1) % 1000))

# Kill anything using that port
echo -e "Freeing port $USER_PORT..."
fuser -k "${USER_PORT}/tcp" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Freed port $USER_PORT${NC}"
else
    echo -e "No process was using port $USER_PORT"
fi

# Step 4: Final verification
echo -e "\n${YELLOW}Step 4: Verifying shutdown...${NC}"
REMAINING=$(ps aux | grep "green-boy.py" | grep -v grep | grep "$CURRENT_USER")

if [ -z "$REMAINING" ]; then
    echo -e "${GREEN}✓ All Green-Boy processes successfully terminated!${NC}"
else
    echo -e "${RED}⚠️ Some processes might still be running:${NC}"
    echo "$REMAINING"
    echo -e "You may need to manually investigate these processes."
fi

echo -e "\n${GREEN}Emergency shutdown procedure completed.${NC}"
echo -e "To restart Green-Boy later, run: ${YELLOW}python3 green-boy.py${NC}"
