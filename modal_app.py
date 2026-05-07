import modal
import os
from pathlib import Path

# Create a Modal app
app = modal.App("colorizer-app")

# Create persistent volumes
data_volume = modal.Volume.from_name("colorizer-data", create_if_missing=True)
uploads_volume = modal.Volume.from_name("colorizer-uploads", create_if_missing=True)
results_volume = modal.Volume.from_name("colorizer-results", create_if_missing=True)

# Define the image with all necessary dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "flask",
        "flask-cors",
        "flask-login",
        "werkzeug",
        "opencv-python-headless",
        "numpy",
        "psycopg2-binary",
        "pyotp",
        "qrcode",
        "Pillow",
        "python-dotenv",
        "requests",
        "gunicorn",
        "psutil",
        "cloudinary"
    )
    .add_local_dir(Path(__file__).parent / "colorizer", remote_path="/root/colorizer")
)

# Optional: Mount the .env file specifically if it's in the root
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    image = image.add_local_file(env_path, remote_path="/root/colorizer/.env")

@app.function(
    image=image,
    volumes={
        "/data": data_volume,
        "/root/colorizer/static/uploads": uploads_volume,
        "/root/colorizer/static/results": results_volume
    },
    cpu=1.0,
    memory=1024,
    timeout=600,
)
@modal.wsgi_app()
def flask_app():
    import sys
    import os
    
    # Set the working directory to the project root in the container
    os.chdir("/root/colorizer")
    sys.path.append("/root/colorizer")
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Redirect SQLite database to the persistent volume
    os.environ["SQLITE_DB_PATH"] = "/data/app.db"
    
    # Ensure model directory is set correctly
    os.environ["COLORIZER_MODEL_DIR"] = "/root/colorizer/models"
    
    # Initialize DB (creates tables if missing)
    from database import init_db
    init_db()
    
    from app import app as flask_app
    return flask_app

if __name__ == "__main__":
    app.serve()
