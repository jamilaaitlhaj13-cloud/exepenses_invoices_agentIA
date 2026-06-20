# backend_fastapi/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from routers import auth, invoices

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SmartExpenseAgent API",
    description="Invoice and expense management API — powered by DiT + Azure AI + LangChain",
    version="1.0.0",
)

# CORS — adjust origins as needed for your environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],  # Streamlit frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(invoices.router)


@app.get("/")
def root():
    return {"message": "SmartExpenseAgent API is running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}
