# Use a lightweight Python base image
FROM python:3.11-slim

# Set the working directory to /app
WORKDIR /app

# Copy requirements.txt and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files to /app
COPY . .

# Run the bot
CMD ["python", "main.py"]
