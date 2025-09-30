from fastapi import FastAPI

def create_app() -> FastAPI:
    app = FastAPI(title="PCD Service")
    return app


