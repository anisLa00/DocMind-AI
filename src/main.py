from fastapi import FastAPI
from src.routers.users import user_router
from src.routers.auth import auth_router
from src.routers.documents import document_router

app= FastAPI(
    title="DocMind_AI",
    description="AI-powered document assistant using RAG",
    version="1.0.0",
)
@app.get("/")
def root():
    return {"message":"DocMind AI API is running"}


app.include_router(user_router)
app.include_router(auth_router)
app.include_router(document_router)