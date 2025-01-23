# Use the official Python image from the Docker Hub
FROM python:3.13

# Set the working directory in the container
WORKDIR /app

# Copy the requirements.txt file into the container at /app
COPY requirements.txt .

# Install the dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
COPY ./src .

# Specify the command to run the application
CMD ["python", "main.py"]