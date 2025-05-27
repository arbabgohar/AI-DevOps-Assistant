#!/bin/bash

# Check if service name is provided
if [ -z "$1" ]; then
    echo "Error: Service name not provided"
    echo "Usage: $0 <service-name>"
    exit 1
fi

SERVICE_NAME=$1

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root or with sudo"
    exit 1
fi

# Restart the service
echo "Restarting $SERVICE_NAME..."
systemctl restart $SERVICE_NAME

# Check the status
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "$SERVICE_NAME restarted successfully"
    exit 0
else
    echo "Error: Failed to restart $SERVICE_NAME"
    echo "Service status:"
    systemctl status $SERVICE_NAME
    exit 1
fi 