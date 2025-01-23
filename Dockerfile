# Build stage
FROM python:3.13 AS builder

# Set the working directory in the container
WORKDIR /app

# Copy the requirements.txt file into the container at /app
COPY requirements.txt .

# Install the dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/

# Copy application code
COPY ./src .

# Specify the command to run the application
CMD ["python", "main.py"]