from app.database import Base, engine
from app.models.jobs import Job  # Make sure this imports your Job model

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Tables created successfully!")
