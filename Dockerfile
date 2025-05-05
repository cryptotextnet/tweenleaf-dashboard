# Use the official slim Python image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy and install Python dependencies first (caching)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of your app
COPY . .

# Expose port and run with Flask’s built-in server
EXPOSE 8080
CMD ["python3", "app.py"]

