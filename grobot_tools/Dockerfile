# 1. Use an official Python runtime as a parent image
FROM python:3.11-slim

# 2. Set the working directory in the container
WORKDIR /app

# 3. Copy the requirements file into the container
COPY requirements.txt .

# 4. Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the application's code and supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY ./file_tools /app/file_tools
COPY ./time_tool /app/time_tool

# 6. Define the command to run the application using Supervisor
# -n runs it in the foreground, which is required for Docker containers.
CMD ["/usr/local/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/supervisord.conf"]